"""FastAPI application for the ReAgent server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reagent.server.config import server_config
from reagent.server.deps import set_storage
from reagent.storage.sqlite import SQLiteStorage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    storage = SQLiteStorage(db_path=server_config.db_path)
    set_storage(storage)
    yield
    storage.close()


app = FastAPI(
    title="ReAgent Server",
    description="Self-hosted backend for ReAgent trace collection and querying",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
from reagent.server.routes import register_routes  # noqa: E402

register_routes(app)
