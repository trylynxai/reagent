"""Server configuration loaded from environment variables."""

from __future__ import annotations

import os


class ServerAppConfig:
    """Configuration for the ReAgent server process."""

    def __init__(self) -> None:
        self.host: str = os.environ.get("REAGENT_SERVER_HOST", "0.0.0.0")
        self.port: int = int(os.environ.get("REAGENT_SERVER_PORT", "8080"))
        self.db_path: str = os.environ.get("REAGENT_SERVER_DB", "reagent_server.db")

        # Comma-separated list of valid API keys. Empty = no auth required (dev mode).
        keys_raw = os.environ.get("REAGENT_API_KEYS", "")
        self.api_keys: list[str] = [k.strip() for k in keys_raw.split(",") if k.strip()]


server_config = ServerAppConfig()
