"""Event buffer for batching and backpressure handling."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Generic, TypeVar

from reagent.core.constants import BackpressurePolicy, DEFAULT_BUFFER_SIZE
from reagent.core.exceptions import BufferError

T = TypeVar("T")


class EventBuffer(Generic[T]):
    """Thread-safe ring buffer with configurable backpressure.

    The buffer collects events and flushes them to a handler when:
    - The buffer reaches capacity
    - The flush timeout expires
    - flush() is called explicitly

    Backpressure policies:
    - DROP_OLDEST: Drop oldest events when full
    - DROP_NEWEST: Drop newest events when full
    - BLOCK: Block until space is available
    - RAISE: Raise BufferError when full
    """

    def __init__(
        self,
        capacity: int = DEFAULT_BUFFER_SIZE,
        flush_handler: Callable[[list[T]], None] | None = None,
        flush_interval_ms: int = 100,
        backpressure_policy: BackpressurePolicy = BackpressurePolicy.DROP_OLDEST,
    ) -> None:
        """Initialize the event buffer.

        Args:
            capacity: Maximum number of events to buffer
            flush_handler: Callback to invoke when flushing events
            flush_interval_ms: Auto-flush interval in milliseconds
            backpressure_policy: How to handle buffer overflow
        """
        self._capacity = capacity
        self._flush_handler = flush_handler
        self._flush_interval_ms = flush_interval_ms
        self._policy = backpressure_policy

        self._buffer: deque[T] = deque(maxlen=capacity if backpressure_policy == BackpressurePolicy.DROP_OLDEST else None)
        self._lock = threading.RLock()
        self._not_full = threading.Condition(self._lock)

        # Stats
        self._total_added = 0
        self._total_dropped = 0
        self._total_flushed = 0

        # Auto-flush timer
        self._timer: threading.Timer | None = None
        self._last_flush_time = time.time()
        self._running = True

        if flush_interval_ms > 0:
            self._start_flush_timer()

    def add(self, event: T) -> bool:
        """Add an event to the buffer.

        Args:
            event: Event to add

        Returns:
            True if event was added, False if dropped

        Raises:
            BufferError: If policy is RAISE and buffer is full
        """
        with self._not_full:
            if len(self._buffer) >= self._capacity:
                if self._policy == BackpressurePolicy.DROP_OLDEST:
                    # deque with maxlen handles this automatically
                    pass
                elif self._policy == BackpressurePolicy.DROP_NEWEST:
                    self._total_dropped += 1
                    return False
                elif self._policy == BackpressurePolicy.BLOCK:
                    while len(self._buffer) >= self._capacity and self._running:
                        self._not_full.wait(timeout=0.1)
                    if not self._running:
                        return False
                elif self._policy == BackpressurePolicy.RAISE:
                    raise BufferError(
                        "Buffer is full",
                        {"capacity": self._capacity, "policy": self._policy.value},
                    )

            self._buffer.append(event)
            self._total_added += 1

            # Check if we should flush due to capacity
            if len(self._buffer) >= self._capacity:
                self._do_flush()

            return True

    def add_batch(self, events: list[T]) -> int:
        """Add multiple events to the buffer.

        Args:
            events: Events to add

        Returns:
            Number of events successfully added
        """
        added = 0
        for event in events:
            try:
                if self.add(event):
                    added += 1
            except BufferError:
                break
        return added

    def flush(self) -> list[T]:
        """Flush all events from the buffer.

        Returns:
            List of flushed events
        """
        with self._lock:
            return self._do_flush()

    def _do_flush(self) -> list[T]:
        """Internal flush without acquiring lock."""
        if not self._buffer:
            return []

        events = list(self._buffer)
        self._buffer.clear()
        self._total_flushed += len(events)
        self._last_flush_time = time.time()

        # Notify blocked writers
        self._not_full.notify_all()

        # Call flush handler
        if self._flush_handler and events:
            try:
                self._flush_handler(events)
            except Exception:
                # Log error but don't lose events
                pass

        return events

    def _start_flush_timer(self) -> None:
        """Start the auto-flush timer."""
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

        with self._lock:
            if self._buffer:
                self._do_flush()

        self._start_flush_timer()

    def close(self) -> list[T]:
        """Close the buffer and flush remaining events.

        Returns:
            Remaining events that were flushed
        """
        self._running = False

        if self._timer:
            self._timer.cancel()
            self._timer = None

        with self._not_full:
            self._not_full.notify_all()

        return self.flush()

    @property
    def size(self) -> int:
        """Current number of events in the buffer."""
        with self._lock:
            return len(self._buffer)

    @property
    def capacity(self) -> int:
        """Maximum buffer capacity."""
        return self._capacity

    @property
    def is_full(self) -> bool:
        """Check if buffer is at capacity."""
        with self._lock:
            return len(self._buffer) >= self._capacity

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        with self._lock:
            return len(self._buffer) == 0

    @property
    def stats(self) -> dict[str, int]:
        """Get buffer statistics."""
        with self._lock:
            return {
                "current_size": len(self._buffer),
                "capacity": self._capacity,
                "total_added": self._total_added,
                "total_dropped": self._total_dropped,
                "total_flushed": self._total_flushed,
            }

    def __len__(self) -> int:
        """Return current buffer size."""
        return self.size

    def __enter__(self) -> EventBuffer[T]:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()
