"""FastAPI application factory for the Ondoway Graph API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.auth.routes import router as auth_router
from src.api.dependencies import close_driver, init_driver
from src.api.routes import audio, edges, feedback, graph, nodes, schema, trips


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

    _tour_preview_html = Path(__file__).resolve().parents[2] / "frontend" / "tour-preview.html"

    @app.get("/tour-preview")
    async def tour_preview_page():
        """Phase 1.5 web-first preview: a standalone page that calls /trips/preview
        + /audio/preview so a tour's per-stop narration can be read and heard in a
        browser (no app, no profile)."""
        if not _tour_preview_html.is_file():
            from fastapi import HTTPException

            raise HTTPException(404, "tour preview page not found")
        return FileResponse(str(_tour_preview_html), media_type="text/html")

    @app.get("/api/v1/healthz")
    async def healthz():
        """Report which Neo4j the API is connected to (plus a liveness probe).

        Test fixtures use this to verify they are talking to the *test* instance
        (port 7688) before seeding data, so a dev API (``make api`` → 7687) that
        happens to be listening on the same HTTP port can never be reused and
        seeded with test rows. ``neo4j_port`` is parsed from the configured
        ``NEO4J_URI`` (what the driver connected to); ``neo4j_connected`` runs a
        trivial query to confirm the driver is actually live.
        """
        from urllib.parse import urlparse

        from src.api.dependencies import get_driver
        from src.connection import get_database

        uri = os.getenv("NEO4J_URI", "")
        database = get_database()
        connected = False
        try:
            driver = get_driver()
            with driver.session(database=database) as session:
                session.run("RETURN 1 AS ok").single()
            connected = True
        except Exception:
            connected = False

        return JSONResponse(
            content={
                "status": "ok" if connected else "degraded",
                "neo4j_uri": uri,
                "neo4j_port": urlparse(uri).port,
                "neo4j_database": database,
                "neo4j_connected": connected,
            }
        )

    @app.get("/.well-known/apple-app-site-association")
    async def apple_app_site_association():
        from src.api.auth.config import APPLE_TEAM_ID, BUNDLE_ID

        if not APPLE_TEAM_ID:
            from fastapi import HTTPException

            raise HTTPException(500, "APPLE_TEAM_ID not configured")

        return JSONResponse(
            content={
                "applinks": {
                    "apps": [],
                    "details": [
                        {
                            "appID": f"{APPLE_TEAM_ID}.{BUNDLE_ID}",
                            "paths": ["/auth", "/auth/*"],
                        }
                    ],
                }
            },
            media_type="application/json",
        )

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(graph.router, prefix="/api/v1")
    app.include_router(nodes.router, prefix="/api/v1")
    app.include_router(edges.router, prefix="/api/v1")
    app.include_router(schema.router, prefix="/api/v1")
    app.include_router(audio.router, prefix="/api/v1")
    app.include_router(trips.router, prefix="/api/v1")
    app.include_router(feedback.router, prefix="/api/v1")

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
