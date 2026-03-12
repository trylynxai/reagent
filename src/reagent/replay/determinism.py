"""Determinism controls for replay."""

from __future__ import annotations

import random
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator
from unittest.mock import patch


class VirtualClock:
    """Virtual clock for time virtualization during replay.

    Freezes time at recorded timestamps to ensure deterministic behavior.
    """

    def __init__(self) -> None:
        self._frozen_time: datetime | None = None
        self._frozen_timestamp: float | None = None
        self._patches: list[Any] = []

    def freeze(self, timestamp: datetime) -> None:
        """Freeze time at the given timestamp.

        Args:
            timestamp: Time to freeze at
        """
        self._frozen_time = timestamp
        self._frozen_timestamp = timestamp.timestamp()

    def unfreeze(self) -> None:
        """Unfreeze time (return to real time)."""
        self._frozen_time = None
        self._frozen_timestamp = None

    @property
    def is_frozen(self) -> bool:
        """Check if time is frozen."""
        return self._frozen_time is not None

    @property
    def current_time(self) -> datetime:
        """Get current time (frozen or real)."""
        if self._frozen_time is not None:
            return self._frozen_time
        return datetime.utcnow()

    @property
    def current_timestamp(self) -> float:
        """Get current timestamp (frozen or real)."""
        if self._frozen_timestamp is not None:
            return self._frozen_timestamp
        return time.time()

    @contextmanager
    def frozen_at(self, timestamp: datetime) -> Iterator[None]:
        """Context manager to temporarily freeze time.

        Args:
            timestamp: Time to freeze at
        """
        self.freeze(timestamp)
        try:
            yield
        finally:
            self.unfreeze()

    def install_patches(self) -> None:
        """Install time patches for common time functions.

        Patches:
        - datetime.datetime.now()
        - datetime.datetime.utcnow()
        - time.time()
        """

        def fake_now(tz: Any = None) -> datetime:
            if self._frozen_time is not None:
                return self._frozen_time
            return datetime.now(tz)

        def fake_utcnow() -> datetime:
            if self._frozen_time is not None:
                return self._frozen_time
            return datetime.utcnow()

        def fake_time() -> float:
            if self._frozen_timestamp is not None:
                return self._frozen_timestamp
            return time.time()

        # Note: In production, you'd use time-machine or freezegun
        # Here we provide the interface
        pass

    def uninstall_patches(self) -> None:
        """Uninstall time patches."""
        for p in self._patches:
            p.stop()
        self._patches.clear()


class RandomStateManager:
    """Manager for random state capture and restoration.

    Ensures deterministic random number generation during replay.
    """

    def __init__(self) -> None:
        self._captured_state: tuple[Any, ...] | None = None
        self._original_state: tuple[Any, ...] | None = None

    def capture(self) -> tuple[Any, ...]:
        """Capture the current random state.

        Returns:
            Random state tuple
        """
        state = random.getstate()
        self._captured_state = state
        return state

    def restore(self, state: tuple[Any, ...] | None = None) -> None:
        """Restore random state.

        Args:
            state: State to restore (uses captured state if None)
        """
        state_to_restore = state or self._captured_state
        if state_to_restore is not None:
            random.setstate(state_to_restore)

    def set_seed(self, seed: int) -> None:
        """Set random seed for deterministic generation.

        Args:
            seed: Seed value
        """
        random.seed(seed)
        self._captured_state = random.getstate()

    @contextmanager
    def deterministic(self, seed: int | None = None, state: tuple[Any, ...] | None = None) -> Iterator[None]:
        """Context manager for deterministic random generation.

        Args:
            seed: Optional seed to use
            state: Optional state to restore
        """
        self._original_state = random.getstate()

        if state is not None:
            random.setstate(state)
        elif seed is not None:
            random.seed(seed)

        try:
            yield
        finally:
            if self._original_state is not None:
                random.setstate(self._original_state)


class DeterminismController:
    """Controller for all determinism features.

    Combines time virtualization, random state management,
    and other determinism controls.
    """

    def __init__(self) -> None:
        self.clock = VirtualClock()
        self.random = RandomStateManager()
        self._active = False

    def activate(
        self,
        timestamp: datetime | None = None,
        random_seed: int | None = None,
        random_state: tuple[Any, ...] | None = None,
    ) -> None:
        """Activate determinism controls.

        Args:
            timestamp: Time to freeze at
            random_seed: Random seed to use
            random_state: Random state to restore
        """
        self._active = True

        if timestamp is not None:
            self.clock.freeze(timestamp)

        if random_state is not None:
            self.random.restore(random_state)
        elif random_seed is not None:
            self.random.set_seed(random_seed)

    def deactivate(self) -> None:
        """Deactivate determinism controls."""
        self._active = False
        self.clock.unfreeze()

    @property
    def is_active(self) -> bool:
        """Check if determinism controls are active."""
        return self._active

    @contextmanager
    def controlled(
        self,
        timestamp: datetime | None = None,
        random_seed: int | None = None,
    ) -> Iterator[None]:
        """Context manager for deterministic execution.

        Args:
            timestamp: Time to freeze at
            random_seed: Random seed to use
        """
        self.activate(timestamp=timestamp, random_seed=random_seed)
        try:
            yield
        finally:
            self.deactivate()
