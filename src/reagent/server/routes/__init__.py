"""Route registration for the ReAgent server."""

from __future__ import annotations

from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    from reagent.server.routes.health import router as health_router
    from reagent.server.routes.ingest import router as ingest_router
    from reagent.server.routes.runs import router as runs_router
    from reagent.server.routes.search import router as search_router
    from reagent.server.routes.failures import router as failures_router
    from reagent.server.routes.stats import router as stats_router

    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(runs_router)
    app.include_router(search_router)
    app.include_router(failures_router)
    app.include_router(stats_router)
