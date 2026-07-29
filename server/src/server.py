from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from src.authentication.deps import AuthedAccount, require_account
from src.components.config import get_settings
from src.components.db import close_driver, graph_session, init_db
from src.components.logging import configure_logging
from src.tools.registry import mcp
from src.routers import (
    admin, attachments_api, auth, backup_api, entra, focus_api, graph_api, kit_api, manage,
    recall, review, secrets, signup, skills,
)
from src.components.embeddings import warmup

_STATIC = Path(__file__).parent / "static"
_INSTALL_ZIP = Path(__file__).parent.parent / "hivemind-install.zip"
_log = logging.getLogger("hivemind")

mcp_app = mcp.http_app(path="/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    _log.info("HiveMind starting", extra={"path": f"env={settings.ENV}"})
    if not settings.is_dev and settings.NEO4J_PASSWORD in ("", "change-me-neo4j", "test", "testpassword"):
        _log.warning("NEO4J_PASSWORD is a weak/default value in a non-dev environment — set a strong one")
    init_db()
    # System instructions are repo-maintained: refresh the seeded system memory in every org.
    from src.components import seed as seed_service
    with graph_session() as session:
        seed_service.seed_all(session)
    warmup()
    async with mcp_app.lifespan(app):
        yield
    close_driver()


app = FastAPI(title="HiveMind", lifespan=lifespan)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """One structured log line per request; unhandled errors become a clean 500."""
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # truly unhandled — HTTPException/ValueError are caught by handlers below
        _log.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
        return JSONResponse({"detail": "internal server error"}, status_code=500)
    _log.info("request", extra={"method": request.method, "path": request.url.path,
                                "status": response.status_code,
                                "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Services raise ValueError for bad input — surface it as a 400 (safety net; routers may
    also catch it explicitly)."""
    return JSONResponse({"detail": str(exc)}, status_code=400)

app.include_router(admin.router)
app.include_router(manage.router)
app.include_router(signup.router)
app.include_router(auth.router)
app.include_router(recall.router)
app.include_router(secrets.router)
app.include_router(graph_api.router)
app.include_router(review.router)
app.include_router(entra.router)
app.include_router(skills.router)
app.include_router(focus_api.router)
app.include_router(kit_api.router)
app.include_router(attachments_api.router)
app.include_router(backup_api.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/install.zip")
def install_zip(account: AuthedAccount = Depends(require_account)):
    """The self-install kit for a Claude Code project (any authed account can download it)."""
    if not _INSTALL_ZIP.exists():
        raise HTTPException(status_code=404, detail="install package not bundled")
    return FileResponse(_INSTALL_ZIP, media_type="application/zip",
                        filename="hivemind-install.zip")


@app.get("/ui", response_class=HTMLResponse)
def ui():
    """The hive GUI: click through the mind, handle chores, review, manage accounts."""
    return (_STATIC / "index.html").read_text()


# Mounted last so named routes win; the MCP endpoint lives at /mcp.
app.mount("/", mcp_app)
