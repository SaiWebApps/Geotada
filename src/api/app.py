"""FastAPI application factory for the Travlr Graph API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.dependencies import close_driver, init_driver
from src.api.routes import edges, graph, nodes, schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: manage Neo4j driver lifecycle."""
    init_driver()
    yield
    close_driver()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Travlr Graph API",
        version="0.1.0",
        description="CRUD API for the Travlr Neo4j graph database",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(graph.router, prefix="/api/v1")
    app.include_router(nodes.router, prefix="/api/v1")
    app.include_router(edges.router, prefix="/api/v1")
    app.include_router(schema.router, prefix="/api/v1")

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
