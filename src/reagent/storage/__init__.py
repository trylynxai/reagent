"""Storage module - Backend implementations for trace persistence.

Supports multiple storage backends:
- Memory: In-memory storage for testing
- JSONL: File-based storage (default)
- SQLite: Indexed storage with search
"""

from reagent.storage.base import StorageBackend, RunFilter, Pagination
from reagent.storage.memory import MemoryStorage
from reagent.storage.jsonl import JSONLStorage
from reagent.storage.sqlite import SQLiteStorage

__all__ = [
    "StorageBackend",
    "RunFilter",
    "Pagination",
    "MemoryStorage",
    "JSONLStorage",
    "SQLiteStorage",
]
