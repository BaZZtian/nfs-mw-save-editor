"""Typed staged-edit state interfaces.

This module is an interface artifact for the staged-state cleanup.  The
helpers are intentionally not implemented yet; call sites should not migrate
until the concrete behavior and tests land in the next commit.
"""
from __future__ import annotations

from typing import Generic, TypeVar


K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")


class StagedScalar(Generic[T]):
    """Single staged value with fallback to the current saved value."""

    def current(self, have: T) -> T:
        """Return the staged value, or ``have`` when nothing is staged.

        ``have`` is an intentional call-time fallback; this helper does not
        hold a reference to the saved-state source.
        """
        raise NotImplementedError

    def set(self, value: T) -> None:
        """Stage ``value``."""
        raise NotImplementedError

    def clear(self) -> None:
        """Clear the staged value so reads fall back to ``have``."""
        raise NotImplementedError

    def reset_to(self, have: T) -> None:
        """Stage the current saved value as the explicit wanted value."""
        raise NotImplementedError

    def has_pending(self, have: T) -> bool:
        """Return whether the staged value differs from ``have``."""
        raise NotImplementedError


class StagedMap(Generic[K, V]):
    """Dictionary-like staged values with explicit saved-state fallback."""

    def current(self, have: dict[K, V]) -> dict[K, V]:
        """Return the staged map, or a copy of ``have`` when nothing is staged.

        ``have`` is an intentional call-time fallback; this helper does not
        hold a reference to the saved-state source.
        """
        raise NotImplementedError

    def ensure(self, have: dict[K, V]) -> dict[K, V]:
        """Ensure a mutable staged map exists, seeded from ``have``."""
        raise NotImplementedError

    def set_item(self, key: K, value: V, have: dict[K, V]) -> None:
        """Stage one item, seeding the map from ``have`` if needed."""
        raise NotImplementedError

    def get_item(self, key: K, have: dict[K, V], default: V) -> V:
        """Read one item from staged state, saved state, or ``default``."""
        raise NotImplementedError

    def clear(self) -> None:
        """Clear the staged map so reads fall back to ``have``."""
        raise NotImplementedError

    def reset_to(self, have: dict[K, V]) -> None:
        """Stage a copy of the full saved map."""
        raise NotImplementedError

    def prune_to_keys(self, keys: set[K], have: dict[K, V]) -> None:
        """Drop staged entries outside ``keys`` and fill missing values from ``have``."""
        raise NotImplementedError

    def has_pending(self, have: dict[K, V]) -> bool:
        """Return whether staged map contents differ from ``have``."""
        raise NotImplementedError


class StagedSnapshotInjections:
    """Typed staged snapshot-injection queue.

    Snapshot injection state is intentionally separate from ``StagedMap``:
    planning depends on stable library order and optional preview entries.
    """

    def mode_for(self, snapshot_id: str) -> str | None:
        """Return the staged target mode for ``snapshot_id``, if any."""
        raise NotImplementedError

    def stage(self, snapshot_id: str, target_mode: str) -> None:
        """Stage one snapshot injection target."""
        raise NotImplementedError

    def clear(self, snapshot_id: str) -> None:
        """Remove one staged snapshot injection, if present."""
        raise NotImplementedError

    def clear_all(self) -> None:
        """Remove every staged snapshot injection."""
        raise NotImplementedError

    def ordered_items(
        self,
        library_snapshot_ids: list[str],
        extra_snapshot_id: str | None = None,
        extra_target_mode: str | None = None,
    ) -> list[tuple[str, str]]:
        """Return staged items ordered by library order, with optional preview item."""
        raise NotImplementedError

    def has_pending(self) -> bool:
        """Return whether any snapshot injection is staged."""
        raise NotImplementedError


class StagedEditState:
    """Composition root for staged edit helpers.

    The helpers store staged UI edits and provide reads with explicit fallback
    to saved values.  They do not orchestrate Apply: consumers remain
    responsible for reading staged values and writing them to ``SaveFile``.

    ``want_slot_flags`` and ``want_cleared_pursuit_slots`` are deliberately not
    represented here.  They remain MainWindow-owned projection caches derived
    from garage transfer state, not independent staged user edits.
    """

    def __init__(self) -> None:
        self.counts: StagedMap[int, int] = StagedMap()
        self.money: StagedScalar[int] = StagedScalar()
        self.profile_alias: StagedScalar[str] = StagedScalar()
        self.parts_levels: StagedMap[int, dict[str, int]] = StagedMap()
        self.parts_masks: StagedMap[int, int] = StagedMap()
        self.slot_bounties: StagedMap[int, int] = StagedMap()
        self.slot_heats: StagedMap[int, int] = StagedMap()
        self.owned_locations: StagedMap[int, int] = StagedMap()
        self.owned_career_slots: StagedMap[int, int] = StagedMap()
        self.snapshot_injections = StagedSnapshotInjections()
