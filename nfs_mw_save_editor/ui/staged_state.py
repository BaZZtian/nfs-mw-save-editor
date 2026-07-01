"""Typed staged-edit state helpers.

This module owns storage primitives for staged UI edits.  Call sites migrate
incrementally; the helpers do not perform SaveFile writes themselves.
"""
from __future__ import annotations

from typing import Generic, TypeVar


K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")


class StagedScalar(Generic[T]):
    """Single staged value with fallback to the current saved value."""

    def __init__(self) -> None:
        self._is_staged = False
        self._value: T | None = None

    def current(self, have: T) -> T:
        """Return the staged value, or ``have`` when nothing is staged.

        ``have`` is an intentional call-time fallback; this helper does not
        hold a reference to the saved-state source.
        """
        return self._value if self._is_staged else have

    def set(self, value: T) -> None:
        """Stage ``value``."""
        self._is_staged = True
        self._value = value

    def clear(self) -> None:
        """Clear the staged value so reads fall back to ``have``."""
        self._is_staged = False
        self._value = None

    def reset_to(self, have: T) -> None:
        """Stage the current saved value as the explicit wanted value."""
        self.set(have)

    def has_pending(self, have: T) -> bool:
        """Return whether the staged value differs from ``have``.

        Pending is value-based.  An explicit ``reset_to(have)`` is staged, but
        it is not pending because applying it would not change saved state.
        """
        return self._is_staged and self._value != have


class StagedMap(Generic[K, V]):
    """Dictionary-like staged values with explicit saved-state fallback."""

    def __init__(self) -> None:
        self._values: dict[K, V] | None = None

    def current(self, have: dict[K, V]) -> dict[K, V]:
        """Return the staged map, or a copy of ``have`` when nothing is staged.

        ``have`` is an intentional call-time fallback; this helper does not
        hold a reference to the saved-state source.
        """
        return dict(self._values if self._values is not None else have)

    def ensure(self, have: dict[K, V]) -> dict[K, V]:
        """Ensure a mutable staged map exists, seeded from ``have``."""
        if self._values is None:
            self._values = dict(have)
        return self._values

    def set_item(self, key: K, value: V, have: dict[K, V]) -> None:
        """Stage one item, seeding the map from ``have`` if needed."""
        self.ensure(have)[key] = value

    def get_item(self, key: K, have: dict[K, V], default: V) -> V:
        """Read one item from staged state, saved state, or ``default``."""
        if self._values is not None and key in self._values:
            return self._values[key]
        return have.get(key, default)

    def clear(self) -> None:
        """Clear the staged map so reads fall back to ``have``."""
        self._values = None

    def reset_to(self, have: dict[K, V]) -> None:
        """Stage a copy of the full saved map."""
        self._values = dict(have)

    def prune_to_keys(self, keys: set[K], have: dict[K, V]) -> None:
        """Drop staged entries outside ``keys`` and fill missing values from ``have``.

        Prune does not create staged state.  If nothing is staged yet, this is
        a no-op so refresh/prune passes cannot create pending changes.
        """
        if self._values is None:
            return
        current = self.current(have)
        self._values = {
            key: (current[key] if key in current else have[key])
            for key in keys
            if key in current or key in have
        }

    def has_pending(self, have: dict[K, V], *, default: V | None = None) -> bool:
        """Return whether staged map contents differ from ``have``.

        Pending is content-based.  A staged dict with the same keys and values
        as ``have`` is not pending, even when it is a distinct object.

        With ``default`` set, comparison is effective-value based over the
        union of staged and ``have`` keys: a key missing from one side counts
        as ``default``.  Use this for sparse maps such as junkman counts,
        where ``get_counts()`` only reports nonzero token ids — staging an
        absent token to 0 is not a pending change.
        """
        if self._values is None:
            return False
        if default is None:
            return self._values != have
        return any(
            self._values.get(key, default) != have.get(key, default)
            for key in self._values.keys() | have.keys()
        )


class StagedSnapshotInjections:
    """Typed staged snapshot-injection queue.

    Snapshot injection state is intentionally separate from ``StagedMap``:
    planning depends on stable library order and optional preview entries.
    """

    def __init__(self) -> None:
        self._items: dict[str, str] = {}

    def mode_for(self, snapshot_id: str) -> str | None:
        """Return the staged target mode for ``snapshot_id``, if any."""
        return self._items.get(str(snapshot_id))

    def stage(self, snapshot_id: str, target_mode: str) -> None:
        """Stage one snapshot injection target."""
        self._items[str(snapshot_id)] = str(target_mode)

    def clear(self, snapshot_id: str) -> None:
        """Remove one staged snapshot injection, if present."""
        self._items.pop(str(snapshot_id), None)

    def clear_all(self) -> None:
        """Remove every staged snapshot injection."""
        self._items.clear()

    def ordered_items(
        self,
        library_snapshot_ids: list[str],
        extra_snapshot_id: str | None = None,
        extra_target_mode: str | None = None,
    ) -> list[tuple[str, str]]:
        """Return staged items ordered by library order, with optional preview item.

        When ``extra_snapshot_id`` matches an already staged id, the preview
        target overrides the staged target in the returned list only; stored
        staged state is not mutated.  The two extra fields must be provided
        together because a preview entry is only valid as an id/mode pair.
        """
        if (extra_snapshot_id is None) != (extra_target_mode is None):
            raise ValueError("extra_snapshot_id and extra_target_mode must be provided together")
        items = dict(self._items)
        if extra_snapshot_id is not None and extra_target_mode is not None:
            items[str(extra_snapshot_id)] = str(extra_target_mode)

        ordered: list[tuple[str, str]] = []
        seen: set[str] = set()
        for snapshot_id in library_snapshot_ids:
            key = str(snapshot_id)
            if key in items:
                ordered.append((key, items[key]))
                seen.add(key)
        for snapshot_id, target_mode in items.items():
            if snapshot_id not in seen:
                ordered.append((snapshot_id, target_mode))
        return ordered

    def has_pending(self) -> bool:
        """Return whether any snapshot injection is staged."""
        return bool(self._items)


class StagedEditState:
    """Composition root for staged edit helpers.

    The helpers store staged UI edits and provide reads with explicit fallback
    to saved values.  They do not orchestrate Apply: consumers remain
    responsible for reading staged values and writing them to ``SaveFile``.

    Pursuit slot-flag projections are deliberately not represented here.
    They are derived from garage transfer state on demand, not independent
    staged user edits (the former ``want_slot_flags`` /
    ``want_cleared_pursuit_slots`` caches were removed as dead state).
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
