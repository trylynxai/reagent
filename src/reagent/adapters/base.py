"""Base adapter interface for framework integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from reagent.core.exceptions import AdapterError

if TYPE_CHECKING:
    from reagent.client.reagent import ReAgent


class Adapter(ABC):
    """Base class for framework adapters.

    Adapters provide automatic instrumentation for specific
    AI agent frameworks (LangChain, OpenAI, etc.).
    """

    def __init__(self, client: ReAgent) -> None:
        """Initialize the adapter.

        Args:
            client: ReAgent client instance
        """
        self._client = client
        self._installed = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the adapter name."""
        pass

    @property
    @abstractmethod
    def framework(self) -> str:
        """Get the framework name."""
        pass

    @property
    def is_installed(self) -> bool:
        """Check if adapter is installed."""
        return self._installed

    @abstractmethod
    def install(self) -> None:
        """Install the adapter hooks.

        This should set up callbacks, wrappers, or patches
        to intercept framework events.
        """
        pass

    @abstractmethod
    def uninstall(self) -> None:
        """Uninstall the adapter hooks.

        This should restore the original behavior.
        """
        pass

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Check if the framework is available for instrumentation.

        Returns:
            True if the framework is installed and compatible
        """
        pass

    @classmethod
    def get_framework_version(cls) -> str | None:
        """Get the installed framework version.

        Returns:
            Version string or None if not installed
        """
        return None


class AdapterRegistry:
    """Registry for managing framework adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, type[Adapter]] = {}
        self._instances: dict[str, Adapter] = {}

    def register(self, adapter_class: type[Adapter]) -> None:
        """Register an adapter class.

        Args:
            adapter_class: Adapter class to register
        """
        # Create temp instance to get name
        class TempAdapter(adapter_class):
            def install(self) -> None:
                pass
            def uninstall(self) -> None:
                pass
            @classmethod
            def is_available(cls) -> bool:
                return True

        # Get name from class property
        name = adapter_class.__name__
        self._adapters[name] = adapter_class

    def get(self, name: str) -> type[Adapter] | None:
        """Get an adapter class by name.

        Args:
            name: Adapter name

        Returns:
            Adapter class or None
        """
        return self._adapters.get(name)

    def list_available(self) -> list[str]:
        """List available adapters (frameworks installed).

        Returns:
            List of adapter names
        """
        return [
            name
            for name, adapter_class in self._adapters.items()
            if adapter_class.is_available()
        ]

    def install(self, name: str, client: ReAgent) -> Adapter:
        """Install an adapter.

        Args:
            name: Adapter name
            client: ReAgent client

        Returns:
            Installed adapter instance

        Raises:
            AdapterError: If adapter not found or installation fails
        """
        adapter_class = self._adapters.get(name)
        if adapter_class is None:
            raise AdapterError(f"Adapter not found: {name}")

        if not adapter_class.is_available():
            raise AdapterError(
                f"Framework not available for adapter: {name}",
                {"adapter": name, "framework": adapter_class.__name__},
            )

        instance = adapter_class(client)
        instance.install()
        self._instances[name] = instance
        return instance

    def uninstall(self, name: str) -> bool:
        """Uninstall an adapter.

        Args:
            name: Adapter name

        Returns:
            True if uninstalled, False if not found
        """
        instance = self._instances.get(name)
        if instance is None:
            return False

        instance.uninstall()
        del self._instances[name]
        return True

    def uninstall_all(self) -> None:
        """Uninstall all adapters."""
        for name in list(self._instances.keys()):
            self.uninstall(name)


# Global registry
_registry = AdapterRegistry()


def get_registry() -> AdapterRegistry:
    """Get the global adapter registry."""
    return _registry
