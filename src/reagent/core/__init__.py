"""Core module - Foundation for ReAgent.

Contains exceptions, constants, and configuration management.
"""

from reagent.core.exceptions import (
    ReAgentError,
    ConfigError,
    StorageError,
    ReplayError,
    RedactionError,
    AdapterError,
    BufferError,
    TransportError,
    ValidationError,
)
from reagent.core.constants import EventType, TransportMode, Status, BackpressurePolicy
from reagent.core.config import Config, StorageConfig, RedactionConfig, ReplayConfig

__all__ = [
    # Exceptions
    "ReAgentError",
    "ConfigError",
    "StorageError",
    "ReplayError",
    "RedactionError",
    "AdapterError",
    "BufferError",
    "TransportError",
    "ValidationError",
    # Constants
    "EventType",
    "TransportMode",
    "Status",
    "BackpressurePolicy",
    # Config
    "Config",
    "StorageConfig",
    "RedactionConfig",
    "ReplayConfig",
]
