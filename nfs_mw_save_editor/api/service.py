"""Staged-edit service over the core SaveFile — the state authority.

One EditorService instance = one editing session. All mutations stage in
this layer first; the in-memory SaveFile changes only on apply, the disk
only on save. The frontend never re-derives a game rule: validation happens
here, through core calls, and refusals surface as typed ApiError.

Validation strategy (pinned): staged values are validated at stage time by
dry-running the real core setter on a scratch copy of the save bytes.
The scratch SaveFile costs ~63KB per call and guarantees the service can
never accept a value the core would later refuse at apply time. Error
classing without message-sniffing:

- money: the pydantic param model already enforces the u32 bound (the same
  bound the Qt editor and core `_require_u32` enforce); anything the core
  still refuses is INTERNAL.
- slot heat: value non-finite or outside the core's own
  GARAGE_HEAT_MIN..GARAGE_HEAT_MAX constants -> INVALID_VALUE; unknown
  slot_index -> INVALID_VALUE; otherwise a core refusal is, by
  construction, the story-progression cap -> BLOCKED, message = the core's
  ValueError text verbatim (it names the Blacklist rank and the cap).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from core.savefile import SaveFile

from .schema import ApiErrorCode, SaveResult, SaveState


class ApiError(Exception):
    """Typed failure crossing the boundary; the server maps it to JSON-RPC."""

    def __init__(self, code: ApiErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EditorService:
    """Session state: an open SaveFile plus staged (unapplied) edits.

    Staged storage is plain want-maps; `have` values are always read from
    the live SaveFile at state-build time, never cached, so a staged entry
    that equals the current value simply disappears from StagedInfo
    (mirrors the Qt want==have convention).
    """

    def __init__(self) -> None:
        self._savefile: Optional[SaveFile] = None
        self._staged_money: Optional[int] = None
        self._staged_heat: Dict[int, float] = {}

    # -- session ----------------------------------------------------------

    def open_save(self, path: str) -> SaveState:
        """Load `path` read-only into memory and return the full state.

        ALREADY_OPEN if a save is open (v0 contract: explicit close first,
        no silent replace — protects staged edits from a stray dialog).
        IO_ERROR when the file is missing/unreadable; the core's layout
        validation errors also surface as IO_ERROR with the core message.
        Opening never modifies the file (project safety rule).
        """
        raise NotImplementedError("stage A scaffold")

    def close_save(self) -> SaveState:
        """Drop the session including staged edits; returns opened=False.

        Deliberately NOT guarded by dirty-state: the confirm-discard
        question is UI policy, the frontend asks it (contract note so the
        renderer knows the guard is its job).
        """
        raise NotImplementedError("stage A scaffold")

    def get_state(self) -> SaveState:
        """Assemble the whole-truth SaveState from the live SaveFile.

        Garage list = occupied entries of `get_garage_slots()`; heat cap
        from `get_story_heat_cap()`. Degraded sub-reads (e.g. garage
        detection failure) do not fail the call: the affected list comes
        back empty and the reason lands in `warnings` — same policy as the
        Qt main window.
        """
        raise NotImplementedError("stage A scaffold")

    # -- staged edits ------------------------------------------------------

    def set_money(self, value: int) -> SaveState:
        """Stage a money edit (does not touch SaveFile bytes)."""
        raise NotImplementedError("stage A scaffold")

    def set_slot_heat(self, slot_index: int, value: float) -> SaveState:
        """Stage a heat edit for one career slot; dry-run validated.

        Over-cap raises BLOCKED with the core's reason (never clamps —
        silent clamping is banned by the state/safety rules).
        """
        raise NotImplementedError("stage A scaffold")

    def reset_staged(self) -> SaveState:
        """Discard all staged edits; the SaveFile buffer is untouched."""
        raise NotImplementedError("stage A scaffold")

    # -- apply / persist ---------------------------------------------------

    def apply_staged(self) -> SaveState:
        """Write staged wants into the in-memory SaveFile via core setters.

        Order: money first, then heats ascending by slot (deterministic
        for tests). After apply the staged maps are empty and
        `applied_not_saved` reflects a byte compare of buffer vs disk.
        A core refusal here is INTERNAL by definition: stage-time dry-run
        must have caught it (that invariant is what the scratch-copy
        strategy buys).
        """
        raise NotImplementedError("stage A scaffold")

    def save_with_backup(self) -> SaveResult:
        """Apply staged edits (if any), then SaveFile.save(make_backup=True).

        The core owns the backup file and integrity repair. Afterwards the
        session is clean: no staged entries, applied_not_saved False.
        Disk failures surface as IO_ERROR; the in-memory state stays
        intact so the user can retry.
        """
        raise NotImplementedError("stage A scaffold")

    # -- internals ---------------------------------------------------------

    def _require_open(self) -> SaveFile:
        """Return the live SaveFile or raise SAVE_NOT_OPEN."""
        raise NotImplementedError("stage A scaffold")

    def _dry_run_scratch(self) -> SaveFile:
        """SaveFile over a copy of the current buffer, for validation only."""
        raise NotImplementedError("stage A scaffold")

    def _applied_not_saved(self) -> bool:
        """Byte-compare in-memory buffer vs the file on disk."""
        raise NotImplementedError("stage A scaffold")
