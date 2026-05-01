"""FastAPI application factory for the Ondoway Graph API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.dependencies import close_driver, init_driver
from src.api.auth.routes import router as auth_router
from src.api.routes import audio, edges, graph, nodes, schema, trips


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: manage Neo4j driver lifecycle."""
    init_driver()
    yield
    close_driver()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ondoway Graph API",
        version="0.1.0",
        description="CRUD API for the Ondoway Neo4j graph database",
        lifespan=lifespan,
    )

    origins = os.getenv("CORS_ORIGINS", "*").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _auth_html = Path(__file__).resolve().parents[2] / "frontend" / "auth.html"

    @app.get("/auth")
    async def auth_redirect():
        if not _auth_html.is_file():
            from fastapi import HTTPException
            raise HTTPException(404, "auth redirect page not found")
        return FileResponse(str(_auth_html), media_type="text/html")

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(graph.router, prefix="/api/v1")
    app.include_router(nodes.router, prefix="/api/v1")
    app.include_router(edges.router, prefix="/api/v1")
    app.include_router(schema.router, prefix="/api/v1")
    app.include_router(audio.router, prefix="/api/v1")
    app.include_router(trips.router, prefix="/api/v1")

    # Serve the graph editor frontend
    editor_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "frontend",
        "editor",
    )
    if os.path.isdir(editor_dir):
        app.mount("/editor", StaticFiles(directory=editor_dir, html=True), name="editor")

    return app


app = create_app()
