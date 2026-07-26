from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.db.neo4j import close_driver, init_db
from src.mcp_server.tools import mcp
from src.routers import admin, graph_api, manage, recall, review, secrets, signup
from src.services.embeddings import warmup

_STATIC = Path(__file__).parent / "static"

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
app.include_router(recall.router)
app.include_router(secrets.router)
app.include_router(graph_api.router)
app.include_router(review.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ui", response_class=HTMLResponse)
def ui():
    """The hive GUI: click through the mind, handle chores, review, manage accounts."""
    return (_STATIC / "index.html").read_text()


# Mounted last so named routes win; the MCP endpoint lives at /mcp.
app.mount("/", mcp_app)
