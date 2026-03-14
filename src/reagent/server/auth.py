"""API key authentication for the ReAgent server."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from reagent.server import config as config_mod


def verify_api_key(request: Request) -> None:
    """FastAPI dependency that checks the Bearer token against configured API keys.

    If no API keys are configured (dev mode), all requests are allowed.
    """
    cfg = config_mod.server_config
    if not cfg.api_keys:
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]
    if token not in cfg.api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")
