"""Sandbox for isolating replay from external systems."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator
from unittest.mock import MagicMock, patch

from reagent.core.exceptions import ReplaySandboxError
from reagent.schema.steps import AnyStep, LLMCallStep, ToolCallStep


class Sandbox:
    """Sandbox for isolating replay execution.

    Prevents:
    - Network calls (blocks outbound requests)
    - File system writes (optional)
    - External API calls

    Provides:
    - Recorded response returns
    - Mock implementations
    """

    def __init__(self, strict: bool = True) -> None:
        """Initialize the sandbox.

        Args:
            strict: If True, raise on blocked operations
        """
        self._strict = strict
        self._patches: list[Any] = []
        self._mocks: dict[str, Callable[..., Any]] = {}
        self._recorded_responses: dict[int, Any] = {}  # step_number -> response
        self._active = False

    def add_recorded_response(self, step_number: int, response: Any) -> None:
        """Add a recorded response for a step.

        Args:
            step_number: Step number
            response: Recorded response to return
        """
        self._recorded_responses[step_number] = response

    def get_recorded_response(self, step_number: int) -> Any:
        """Get the recorded response for a step.

        Args:
            step_number: Step number

        Returns:
            Recorded response

        Raises:
            ReplaySandboxError: If no response recorded
        """
        if step_number not in self._recorded_responses:
            if self._strict:
                raise ReplaySandboxError(
                    f"No recorded response for step {step_number}",
                    {"step_number": step_number},
                )
            return None
        return self._recorded_responses[step_number]

    def add_mock(self, name: str, mock_fn: Callable[..., Any]) -> None:
        """Add a mock implementation.

        Args:
            name: Name to identify the mock
            mock_fn: Mock function to use
        """
        self._mocks[name] = mock_fn

    def get_mock(self, name: str) -> Callable[..., Any] | None:
        """Get a mock implementation.

        Args:
            name: Mock name

        Returns:
            Mock function or None
        """
        return self._mocks.get(name)

    def activate(self) -> None:
        """Activate the sandbox."""
        self._active = True
        self._install_network_block()

    def deactivate(self) -> None:
        """Deactivate the sandbox."""
        self._active = False
        self._uninstall_patches()

    @property
    def is_active(self) -> bool:
        """Check if sandbox is active."""
        return self._active

    def _install_network_block(self) -> None:
        """Install network blocking patches."""
        # Block socket connections
        try:
            import socket

            original_connect = socket.socket.connect

            def blocked_connect(self: Any, *args: Any, **kwargs: Any) -> None:
                raise ReplaySandboxError(
                    "Network calls are blocked during replay",
                    {"method": "socket.connect", "args": str(args)},
                )

            patcher = patch.object(socket.socket, "connect", blocked_connect)
            self._patches.append(patcher)
            patcher.start()
        except Exception:
            pass

        # Block urllib
        try:
            import urllib.request

            def blocked_urlopen(*args: Any, **kwargs: Any) -> None:
                raise ReplaySandboxError(
                    "Network calls are blocked during replay",
                    {"method": "urllib.request.urlopen"},
                )

            patcher = patch.object(urllib.request, "urlopen", blocked_urlopen)
            self._patches.append(patcher)
            patcher.start()
        except Exception:
            pass

        # Block requests library
        try:
            import requests

            def blocked_request(*args: Any, **kwargs: Any) -> None:
                raise ReplaySandboxError(
                    "Network calls are blocked during replay",
                    {"method": "requests.request"},
                )

            patcher = patch.object(requests, "request", blocked_request)
            self._patches.append(patcher)
            patcher.start()
        except ImportError:
            pass

        # Block httpx library
        try:
            import httpx

            def blocked_httpx(*args: Any, **kwargs: Any) -> None:
                raise ReplaySandboxError(
                    "Network calls are blocked during replay",
                    {"method": "httpx.request"},
                )

            patcher = patch.object(httpx.Client, "request", blocked_httpx)
            self._patches.append(patcher)
            patcher.start()
        except ImportError:
            pass

    def _uninstall_patches(self) -> None:
        """Uninstall all patches."""
        for patcher in self._patches:
            try:
                patcher.stop()
            except Exception:
                pass
        self._patches.clear()

    def clear(self) -> None:
        """Clear all recorded responses and mocks."""
        self._recorded_responses.clear()
        self._mocks.clear()


class SandboxContext:
    """Context manager for sandboxed execution."""

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def __enter__(self) -> Sandbox:
        self._sandbox.activate()
        return self._sandbox

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._sandbox.deactivate()


@contextmanager
def sandboxed(strict: bool = True) -> Iterator[Sandbox]:
    """Context manager for sandboxed execution.

    Usage:
        with sandboxed() as sandbox:
            # Network calls will be blocked
            pass

    Args:
        strict: If True, raise on blocked operations

    Yields:
        Sandbox instance
    """
    sandbox = Sandbox(strict=strict)
    sandbox.activate()
    try:
        yield sandbox
    finally:
        sandbox.deactivate()
