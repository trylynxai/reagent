"""ReAgent - AI Agent Debugging & Observability Platform.

Capture, replay, and debug AI agent executions with full fidelity.
"""

from reagent.client.reagent import ReAgent
from reagent.client.context import RunContext
from reagent.core.config import Config
from reagent.core.constants import EventType, TransportMode, Status
from reagent.core.exceptions import (
    ReAgentError,
    ConfigError,
    StorageError,
    ReplayError,
    RedactionError,
    AdapterError,
)

__version__ = "0.1.0"

__all__ = [
    # Main client
    "ReAgent",
    "RunContext",
    # Configuration
    "Config",
    # Constants
    "EventType",
    "TransportMode",
    "Status",
    # Exceptions
    "ReAgentError",
    "ConfigError",
    "StorageError",
    "ReplayError",
    "RedactionError",
    "AdapterError",
    # Version
    "__version__",
]
