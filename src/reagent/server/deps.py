"""FastAPI dependency injection for shared resources."""

from __future__ import annotations

from reagent.storage.sqlite import SQLiteStorage

# Module-level storage instance, set during app lifespan.
_storage: SQLiteStorage | None = None


def set_storage(storage: SQLiteStorage) -> None:
    global _storage
    _storage = storage


def get_storage() -> SQLiteStorage:
    assert _storage is not None, "Storage not initialized"
    return _storage
