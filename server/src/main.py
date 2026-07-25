from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.db.neo4j import close_driver, init_db
from src.mcp_server.tools import mcp
from src.routers import admin, recall, secrets

mcp_app = mcp.http_app(path="/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    async with mcp_app.lifespan(app):
        yield
    close_driver()


app = FastAPI(title="HiveMind", lifespan=lifespan)

app.include_router(admin.router)
app.include_router(recall.router)
app.include_router(secrets.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Mounted last so named routes win; the MCP endpoint lives at /mcp.
app.mount("/", mcp_app)
