"""Alert delivery backends.

Supports webhook (HTTP POST), callback functions, and logging.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Any, Callable

from reagent.alerts.rules import AlertResult

logger = logging.getLogger(__name__)


class AlertDeliveryBackend(ABC):
    """Base class for alert delivery backends."""

    @abstractmethod
    def deliver(self, result: AlertResult) -> None:
        """Deliver an alert result."""


class WebhookDelivery(AlertDeliveryBackend):
    """Deliver alerts via HTTP POST to a webhook URL."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self.timeout_seconds = timeout_seconds

    def deliver(self, result: AlertResult) -> None:
        """Send alert as JSON POST in a background thread."""
        thread = threading.Thread(
            target=self._send,
            args=(result,),
            daemon=True,
        )
        thread.start()

    def _send(self, result: AlertResult) -> None:
        """Perform the HTTP POST."""
        try:
            payload = json.dumps(
                result.model_dump(mode="json"),
                default=str,
            ).encode("utf-8")

            headers = {
                "Content-Type": "application/json",
                **self.headers,
            }

            req = urllib.request.Request(
                self.url,
                data=payload,
                headers=headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.timeout_seconds):
                pass

        except Exception:
            logger.warning(
                "Failed to deliver alert '%s' to %s",
                result.rule_name,
                self.url,
                exc_info=True,
            )


class CallbackDelivery(AlertDeliveryBackend):
    """Deliver alerts by calling a Python function."""

    def __init__(self, callback: Callable[[AlertResult], Any]) -> None:
        self.callback = callback

    def deliver(self, result: AlertResult) -> None:
        """Call the callback with the alert result."""
        try:
            self.callback(result)
        except Exception:
            logger.warning(
                "Alert callback failed for '%s'",
                result.rule_name,
                exc_info=True,
            )


class LogDelivery(AlertDeliveryBackend):
    """Deliver alerts to Python logging."""

    def __init__(self, logger_name: str = "reagent.alerts") -> None:
        self._logger = logging.getLogger(logger_name)

    def deliver(self, result: AlertResult) -> None:
        """Log the alert."""
        level = (
            logging.CRITICAL
            if result.severity.value == "critical"
            else logging.WARNING
        )
        self._logger.log(
            level,
            "[%s] %s (run=%s)",
            result.alert_type.upper(),
            result.message,
            result.run_id,
        )
