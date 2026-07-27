from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from src.authentication.deps import AuthedAccount, require_account
from src.db.neo4j import close_driver, init_db
from src.mcp_server.tools import mcp
from src.routers import admin, auth, entra, graph_api, manage, recall, review, secrets, signup
from src.services.embeddings import warmup

_STATIC = Path(__file__).parent / "static"
_INSTALL_ZIP = Path(__file__).parent.parent / "hivemind-install.zip"

mcp_app = mcp.http_app(path="/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    warmup()
    async with mcp_app.lifespan(app):
        yield
    close_driver()


app = FastAPI(title="HiveMind", lifespan=lifespan)

app.include_router(admin.router)
app.include_router(manage.router)
app.include_router(signup.router)
app.include_router(auth.router)
app.include_router(recall.router)
app.include_router(secrets.router)
app.include_router(graph_api.router)
app.include_router(review.router)
app.include_router(entra.router)


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
