"""Transport layer for delivering events to storage."""

from __future__ import annotations

import json
import queue
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from uuid import UUID

from reagent.core.constants import TransportMode
from reagent.core.exceptions import TransportError
from reagent.schema.events import ExecutionEvent
from reagent.schema.steps import AnyStep
from reagent.schema.run import RunMetadata
from reagent.storage.base import StorageBackend


class Transport(ABC):
    """Abstract base class for event transports."""

    @abstractmethod
    def send_metadata(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Send run metadata."""
        pass

    @abstractmethod
    def send_step(self, run_id: UUID, step: AnyStep) -> None:
        """Send a step event."""
        pass

    @abstractmethod
    def send_batch(self, run_id: UUID, steps: list[AnyStep]) -> None:
        """Send a batch of steps."""
        pass

    @abstractmethod
    def flush(self) -> None:
        """Flush any pending events."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the transport."""
        pass

    @property
    @abstractmethod
    def mode(self) -> TransportMode:
        """Get the transport mode."""
        pass


class SyncTransport(Transport):
    """Synchronous, blocking transport.

    Events are written directly to storage in the calling thread.
    Highest reliability but adds latency to agent execution.
    """

    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    def send_metadata(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Send run metadata synchronously."""
        self._storage.save_run(run_id, metadata)

    def send_step(self, run_id: UUID, step: AnyStep) -> None:
        """Send a step synchronously."""
        self._storage.save_step(run_id, step)

    def send_batch(self, run_id: UUID, steps: list[AnyStep]) -> None:
        """Send a batch of steps synchronously."""
        for step in steps:
            self._storage.save_step(run_id, step)

    def flush(self) -> None:
        """No-op for sync transport."""
        pass

    def close(self) -> None:
        """Close the transport."""
        pass

    @property
    def mode(self) -> TransportMode:
        return TransportMode.SYNC


class AsyncTransport(Transport):
    """Asynchronous transport using a background thread.

    Events are queued and written in a background thread.
    Low latency but best-effort delivery.
    """

    def __init__(
        self,
        storage: StorageBackend,
        max_queue_size: int = 10000,
    ) -> None:
        self._storage = storage
        self._queue: queue.Queue[tuple[str, UUID, Any]] = queue.Queue(maxsize=max_queue_size)
        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def send_metadata(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Queue metadata for async delivery."""
        self._enqueue("metadata", run_id, metadata)

    def send_step(self, run_id: UUID, step: AnyStep) -> None:
        """Queue a step for async delivery."""
        self._enqueue("step", run_id, step)

    def send_batch(self, run_id: UUID, steps: list[AnyStep]) -> None:
        """Queue a batch of steps for async delivery."""
        self._enqueue("batch", run_id, steps)

    def _enqueue(self, msg_type: str, run_id: UUID, data: Any) -> None:
        """Add item to queue, dropping if full."""
        try:
            self._queue.put_nowait((msg_type, run_id, data))
        except queue.Full:
            # Drop event if queue is full
            pass

    def _worker_loop(self) -> None:
        """Background worker loop."""
        while self._running or not self._queue.empty():
            try:
                msg_type, run_id, data = self._queue.get(timeout=0.1)
                self._process_message(msg_type, run_id, data)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                # Log error but continue processing
                pass

    def _process_message(self, msg_type: str, run_id: UUID, data: Any) -> None:
        """Process a queued message."""
        if msg_type == "metadata":
            self._storage.save_run(run_id, data)
        elif msg_type == "step":
            self._storage.save_step(run_id, data)
        elif msg_type == "batch":
            for step in data:
                self._storage.save_step(run_id, step)

    def flush(self) -> None:
        """Wait for queue to be processed."""
        self._queue.join()

    def close(self) -> None:
        """Close the transport and wait for worker."""
        self._running = False
        self.flush()
        self._worker.join(timeout=5.0)

    @property
    def mode(self) -> TransportMode:
        return TransportMode.ASYNC


class BufferedTransport(Transport):
    """Buffered transport that batches writes.

    Events are collected and written in batches.
    Good balance of performance and reliability.
    """

    def __init__(
        self,
        storage: StorageBackend,
        batch_size: int = 100,
        flush_interval_ms: int = 100,
    ) -> None:
        self._storage = storage
        self._batch_size = batch_size
        self._flush_interval_ms = flush_interval_ms

        self._lock = threading.Lock()
        self._metadata_pending: dict[UUID, RunMetadata] = {}
        self._steps_pending: dict[UUID, list[AnyStep]] = {}

        self._running = True
        self._timer: threading.Timer | None = None
        self._start_timer()

    def send_metadata(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Buffer metadata for batch delivery."""
        with self._lock:
            self._metadata_pending[run_id] = metadata

    def send_step(self, run_id: UUID, step: AnyStep) -> None:
        """Buffer a step for batch delivery."""
        with self._lock:
            if run_id not in self._steps_pending:
                self._steps_pending[run_id] = []
            self._steps_pending[run_id].append(step)

            # Flush if batch is full
            if len(self._steps_pending[run_id]) >= self._batch_size:
                self._flush_run(run_id)

    def send_batch(self, run_id: UUID, steps: list[AnyStep]) -> None:
        """Buffer a batch of steps."""
        for step in steps:
            self.send_step(run_id, step)

    def _start_timer(self) -> None:
        """Start the flush timer."""
        if not self._running:
            return

        interval_sec = self._flush_interval_ms / 1000.0
        self._timer = threading.Timer(interval_sec, self._timer_flush)
        self._timer.daemon = True
        self._timer.start()

    def _timer_flush(self) -> None:
        """Timer callback for auto-flush."""
        if not self._running:
            return
        self.flush()
        self._start_timer()

    def _flush_run(self, run_id: UUID) -> None:
        """Flush a specific run's pending data."""
        # Flush metadata first
        if run_id in self._metadata_pending:
            self._storage.save_run(run_id, self._metadata_pending.pop(run_id))

        # Then flush steps
        if run_id in self._steps_pending:
            steps = self._steps_pending.pop(run_id)
            for step in steps:
                self._storage.save_step(run_id, step)

    def flush(self) -> None:
        """Flush all pending data."""
        with self._lock:
            run_ids = list(set(list(self._metadata_pending.keys()) + list(self._steps_pending.keys())))
            for run_id in run_ids:
                self._flush_run(run_id)

    def close(self) -> None:
        """Close the transport."""
        self._running = False
        if self._timer:
            self._timer.cancel()
        self.flush()

    @property
    def mode(self) -> TransportMode:
        return TransportMode.BUFFERED


class OfflineTransport(Transport):
    """Offline transport that queues to disk.

    Events are written to a queue file for later upload.
    Useful for air-gapped environments.
    """

    def __init__(
        self,
        queue_path: str | Path = ".reagent/offline_queue",
        max_file_size_mb: int = 10,
    ) -> None:
        self._queue_path = Path(queue_path).expanduser().resolve()
        self._queue_path.mkdir(parents=True, exist_ok=True)
        self._max_file_size = max_file_size_mb * 1024 * 1024

        self._lock = threading.Lock()
        self._current_file: Path | None = None
        self._current_size = 0

    def _get_queue_file(self) -> Path:
        """Get or create the current queue file."""
        if self._current_file is None or self._current_size >= self._max_file_size:
            timestamp = int(time.time() * 1000)
            self._current_file = self._queue_path / f"queue_{timestamp}.jsonl"
            self._current_size = 0
        return self._current_file

    def _write_event(self, event_type: str, run_id: UUID, data: Any) -> None:
        """Write an event to the queue file."""
        with self._lock:
            queue_file = self._get_queue_file()

            if hasattr(data, "model_dump"):
                data_dict = data.model_dump(mode="json")
            elif isinstance(data, list):
                data_dict = [d.model_dump(mode="json") if hasattr(d, "model_dump") else d for d in data]
            else:
                data_dict = data

            record = {
                "event_type": event_type,
                "run_id": str(run_id),
                "data": data_dict,
                "timestamp": time.time(),
            }

            line = json.dumps(record, default=str) + "\n"
            line_bytes = line.encode("utf-8")

            with open(queue_file, "a") as f:
                f.write(line)

            self._current_size += len(line_bytes)

    def send_metadata(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Queue metadata to disk."""
        self._write_event("metadata", run_id, metadata)

    def send_step(self, run_id: UUID, step: AnyStep) -> None:
        """Queue a step to disk."""
        self._write_event("step", run_id, step)

    def send_batch(self, run_id: UUID, steps: list[AnyStep]) -> None:
        """Queue a batch of steps to disk."""
        self._write_event("batch", run_id, steps)

    def flush(self) -> None:
        """No-op for offline transport (already written to disk)."""
        pass

    def close(self) -> None:
        """Close the transport."""
        pass

    @property
    def mode(self) -> TransportMode:
        return TransportMode.OFFLINE

    def get_pending_files(self) -> list[Path]:
        """Get list of pending queue files."""
        return sorted(self._queue_path.glob("queue_*.jsonl"))

    def upload_pending(self, storage: StorageBackend) -> int:
        """Upload pending events to storage.

        Args:
            storage: Storage backend to upload to

        Returns:
            Number of events uploaded
        """
        uploaded = 0

        for queue_file in self.get_pending_files():
            try:
                with open(queue_file, "r") as f:
                    for line in f:
                        record = json.loads(line)
                        run_id = UUID(record["run_id"])
                        event_type = record["event_type"]
                        data = record["data"]

                        if event_type == "metadata":
                            metadata = RunMetadata.model_validate(data)
                            storage.save_run(run_id, metadata)
                        elif event_type == "step":
                            from reagent.storage.jsonl import STEP_TYPE_MAP, CustomStep
                            step_class = STEP_TYPE_MAP.get(data.get("step_type", "custom"), CustomStep)
                            step = step_class.model_validate(data)
                            storage.save_step(run_id, step)
                        elif event_type == "batch":
                            from reagent.storage.jsonl import STEP_TYPE_MAP, CustomStep
                            for step_data in data:
                                step_class = STEP_TYPE_MAP.get(step_data.get("step_type", "custom"), CustomStep)
                                step = step_class.model_validate(step_data)
                                storage.save_step(run_id, step)

                        uploaded += 1

                # Remove processed file
                queue_file.unlink()

            except Exception:
                # Log error but continue with other files
                pass

        return uploaded


class RemoteTransport(Transport):
    """Remote transport that sends events over HTTP to a ReAgent server.

    Events are buffered in memory and flushed as JSON batches
    to POST /api/v1/ingest via a background thread.
    """

    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        batch_size: int = 50,
        flush_interval_ms: int = 2000,
        timeout_seconds: float = 10.0,
        retry_max: int = 3,
        fallback_to_local: bool = True,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._api_key = api_key
        self._batch_size = batch_size
        self._flush_interval_ms = flush_interval_ms
        self._timeout_seconds = timeout_seconds
        self._retry_max = retry_max
        self._fallback_to_local = fallback_to_local

        self._lock = threading.Lock()
        self._buffer: list[dict[str, Any]] = []
        self._running = True
        self._offline_transport: OfflineTransport | None = None

        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def send_metadata(self, run_id: UUID, metadata: RunMetadata) -> None:
        """Buffer metadata for remote delivery."""
        event = {
            "type": "metadata",
            "run_id": str(run_id),
            "data": metadata.model_dump(mode="json"),
        }
        self._add_to_buffer(event)

    def send_step(self, run_id: UUID, step: AnyStep) -> None:
        """Buffer a step for remote delivery."""
        event = {
            "type": "step",
            "run_id": str(run_id),
            "step_type": step.step_type,
            "data": step.model_dump(mode="json"),
        }
        self._add_to_buffer(event)

    def send_batch(self, run_id: UUID, steps: list[AnyStep]) -> None:
        """Buffer a batch of steps for remote delivery."""
        for step in steps:
            self.send_step(run_id, step)

    def _add_to_buffer(self, event: dict[str, Any]) -> None:
        """Add event to buffer, flush if batch_size reached."""
        with self._lock:
            self._buffer.append(event)
            if len(self._buffer) >= self._batch_size:
                self._flush_buffer()

    def _flush_loop(self) -> None:
        """Background thread that flushes buffer periodically."""
        interval = self._flush_interval_ms / 1000.0
        while self._running:
            time.sleep(interval)
            with self._lock:
                if self._buffer:
                    self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Flush buffered events to the server. Must be called with _lock held."""
        if not self._buffer:
            return

        events = self._buffer[:]
        self._buffer.clear()

        try:
            self._post_batch(events)
        except Exception:
            if self._fallback_to_local:
                self._fallback_write(events)

    def _post_batch(self, events: list[dict[str, Any]]) -> None:
        """POST a batch of events to the server with retry."""
        import urllib.request
        import urllib.error

        url = f"{self._server_url}/api/v1/ingest"
        payload = json.dumps({"events": events}).encode("utf-8")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        last_error: Exception | None = None
        for attempt in range(self._retry_max + 1):
            try:
                req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
                timeout = self._timeout_seconds
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    resp.read()
                return
            except Exception as e:
                last_error = e
                if attempt < self._retry_max:
                    backoff = 2 ** attempt
                    time.sleep(backoff)

        if last_error is not None:
            raise last_error

    def _fallback_write(self, events: list[dict[str, Any]]) -> None:
        """Write events to offline transport as fallback."""
        if self._offline_transport is None:
            self._offline_transport = OfflineTransport()

        for event in events:
            run_id = UUID(event["run_id"])
            if event["type"] == "metadata":
                metadata = RunMetadata.model_validate(event["data"])
                self._offline_transport.send_metadata(run_id, metadata)
            elif event["type"] == "step":
                from reagent.storage.sqlite import STEP_TYPE_MAP, CustomStep
                step_cls = STEP_TYPE_MAP.get(event.get("step_type", "custom"), CustomStep)
                step = step_cls.model_validate(event["data"])
                self._offline_transport.send_step(run_id, step)

    def flush(self) -> None:
        """Flush all pending events."""
        with self._lock:
            self._flush_buffer()

    def close(self) -> None:
        """Close the transport."""
        self._running = False
        self.flush()
        self._flush_thread.join(timeout=5.0)

    @property
    def mode(self) -> TransportMode:
        return TransportMode.REMOTE


def create_transport(mode: TransportMode, storage: StorageBackend, **kwargs: Any) -> Transport:
    """Factory function to create a transport by mode.

    Args:
        mode: Transport mode
        storage: Storage backend
        **kwargs: Additional arguments for the transport

    Returns:
        Configured transport instance
    """
    if mode == TransportMode.SYNC:
        return SyncTransport(storage)
    elif mode == TransportMode.ASYNC:
        return AsyncTransport(storage, **kwargs)
    elif mode == TransportMode.BUFFERED:
        return BufferedTransport(storage, **kwargs)
    elif mode == TransportMode.OFFLINE:
        return OfflineTransport(**kwargs)
    elif mode == TransportMode.REMOTE:
        return RemoteTransport(**kwargs)
    else:
        raise TransportError(f"Unknown transport mode: {mode}")
