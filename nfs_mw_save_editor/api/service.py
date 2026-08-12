"""Staged-edit service over the core SaveFile.

Each instance owns one editing session. Mutations are staged first, applied
to the in-memory buffer explicitly, and written to disk only by save. Core
setters validate staged values on a scratch SaveFile so save-format rules
remain centralized.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from core.savefile import SaveFile

from .schema import (
    ApiErrorCode,
    GarageCar,
    IntegrityInfo,
    RapSheet,
    SaveResult,
    SaveState,
    StagedEntry,
    StagedInfo,
)


class ApiError(Exception):
    """Typed failure crossing the boundary; the server maps it to JSON-RPC."""

    def __init__(self, code: ApiErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EditorService:
    """One open SaveFile plus staged, unapplied edits.

    Current values are read from the live buffer when state is assembled;
    staged entries equal to current values are omitted.
    """

    def __init__(self) -> None:
        self._savefile: Optional[SaveFile] = None
        self._staged_money: Optional[int] = None
        self._staged_heat: Dict[int, float] = {}

    # -- session ----------------------------------------------------------

    def open_save(self, path: str) -> SaveState:
        """Load `path` read-only into memory and return the full state.

        ALREADY_OPEN if a save is open; callers must close explicitly.
        IO_ERROR when the file is missing/unreadable; the core's layout
        validation errors also surface as IO_ERROR with the core message.
        Opening never modifies the file (project safety rule).
        """
        if self._savefile is not None:
            raise ApiError(
                ApiErrorCode.ALREADY_OPEN,
                "a save is already open; close it before opening another",
            )
        try:
            self._savefile = SaveFile.load(path)
        except (OSError, ValueError) as exc:
            raise ApiError(ApiErrorCode.IO_ERROR, str(exc)) from exc
        self._staged_money = None
        self._staged_heat = {}
        return self.get_state()

    def close_save(self) -> SaveState:
        """Drop the session including staged edits; returns opened=False.

        Dirty-state confirmation is a caller responsibility.
        """
        self._savefile = None
        self._staged_money = None
        self._staged_heat = {}
        return self.get_state()

    def get_state(self) -> SaveState:
        """Assemble the whole-truth SaveState from the live SaveFile.

        Garage detection failures degrade to an empty list with a warning;
        other readable state remains available.
        """
        sf = self._savefile
        if sf is None:
            return SaveState(
                opened=False,
                path=None,
                alias=None,
                money=None,
                rap_sheet=None,
                garage=[],
                staged=StagedInfo(dirty=False, applied_not_saved=False, entries=[]),
                integrity=None,
                warnings=[],
            )

        warnings: List[str] = []

        try:
            alias: Optional[str] = sf.get_profile_alias()
        except (ValueError, UnicodeDecodeError) as exc:
            alias = None
            warnings.append(f"profile alias unreadable: {exc}")

        money = sf.get_money()

        rap_sheet: Optional[RapSheet] = None
        totals = sf.get_rap_sheet_totals()
        if totals is not None:
            rap_sheet = RapSheet(
                total_bounty=totals.total_bounty,
                escapes=totals.total_escapes,
                busts=totals.total_busts,
            )
        else:
            warnings.append("rap sheet totals unavailable on this save")

        garage: List[GarageCar] = []
        try:
            heat_cap = sf.get_story_heat_cap()
            for slot in sf.get_garage_slots():
                if not slot.occupied or slot.career_slot == SaveFile.EMPTY_CAREER_SLOT:
                    continue
                garage.append(
                    GarageCar(
                        slot_index=slot.career_slot,
                        model_name=slot.display_name,
                        bounty=slot.bounty,
                        heat=float(slot.heat) if math.isfinite(slot.heat) else None,
                        heat_level=slot.heat_level,
                        heat_cap=heat_cap,
                        source=slot.source_kind,
                    )
                )
        except Exception as exc:  # Garage failures are reported without hiding other state.
            garage = []
            warnings.append(f"garage detection failed: {exc}")

        return SaveState(
            opened=True,
            path=str(sf.path),
            alias=alias,
            money=money,
            rap_sheet=rap_sheet,
            garage=garage,
            staged=self._staged_info(sf),
            integrity=self._integrity_info(sf),
            warnings=warnings,
        )

    # -- staged edits ------------------------------------------------------

    def set_money(self, value: int) -> SaveState:
        """Stage a money edit (does not touch SaveFile bytes)."""
        sf = self._require_open()
        ivalue = int(value)
        if not (0 <= ivalue <= 0xFFFFFFFF):
            raise ApiError(
                ApiErrorCode.INVALID_VALUE, "money must be in range 0..4294967295"
            )
        if ivalue == sf.get_money():
            self._staged_money = None
        else:
            self._staged_money = ivalue
        return self.get_state()

    def set_slot_heat(self, slot_index: int, value: float) -> SaveState:
        """Stage a heat edit for one career slot; dry-run validated.

        Over-cap raises BLOCKED with the core's reason (never clamps —
        silent clamping is banned by the state/safety rules).
        """
        sf = self._require_open()
        slot = int(slot_index)
        heat = float(value)
        if (
            not math.isfinite(heat)
            or heat < SaveFile.GARAGE_HEAT_MIN
            or heat > SaveFile.GARAGE_HEAT_MAX
        ):
            raise ApiError(
                ApiErrorCode.INVALID_VALUE,
                f"heat must be between {SaveFile.GARAGE_HEAT_MIN:.1f} "
                f"and {SaveFile.GARAGE_HEAT_MAX:.1f}",
            )

        scratch = self._dry_run_scratch()
        try:
            current = scratch.get_slot_heat(slot)
        except ValueError as exc:
            raise ApiError(ApiErrorCode.INVALID_VALUE, str(exc)) from exc
        try:
            scratch.set_slot_heat(slot, heat)
        except ValueError as exc:
            # Range and slot existence were pre-checked above, so the only
            # remaining core refusal is the story-progression cap.
            raise ApiError(ApiErrorCode.BLOCKED, str(exc)) from exc

        if math.isfinite(current) and heat == float(current):
            self._staged_heat.pop(slot, None)
        else:
            self._staged_heat[slot] = heat
        return self.get_state()

    def reset_staged(self) -> SaveState:
        """Discard all staged edits; the SaveFile buffer is untouched."""
        self._require_open()
        self._staged_money = None
        self._staged_heat = {}
        return self.get_state()

    # -- apply / persist ---------------------------------------------------

    def apply_staged(self) -> SaveState:
        """Apply staged values through core setters in deterministic order.

        A refusal after scratch validation is reported as INTERNAL. Successful
        apply clears staged maps and derives disk state by byte comparison.
        """
        sf = self._require_open()
        try:
            if self._staged_money is not None:
                sf.set_money(self._staged_money)
            for slot in sorted(self._staged_heat):
                sf.set_slot_heat(slot, self._staged_heat[slot])
        except ValueError as exc:
            raise ApiError(
                ApiErrorCode.INTERNAL, f"apply refused after dry-run: {exc}"
            ) from exc
        self._staged_money = None
        self._staged_heat = {}
        return self.get_state()

    def save_with_backup(self) -> SaveResult:
        """Apply staged edits (if any), then SaveFile.save(make_backup=True).

        The core owns the backup file and integrity repair. Afterwards the
        session is clean: no staged entries, applied_not_saved False.
        Disk failures surface as IO_ERROR; the in-memory state stays
        intact so the user can retry.

        The backup path is detected from the directory before and after the
        core save call because the core API returns only the saved path.
        """
        sf = self._require_open()
        self.apply_staged()

        parent = sf.path.parent
        suffix = sf.path.suffix + ".bak_"
        try:
            before = {p.name for p in parent.glob(sf.path.name + ".bak_*")}
            saved = sf.save(make_backup=True)
            after = [p for p in parent.glob(sf.path.name + ".bak_*") if p.name not in before]
        except OSError as exc:
            raise ApiError(ApiErrorCode.IO_ERROR, str(exc)) from exc
        if not after:
            raise ApiError(
                ApiErrorCode.IO_ERROR,
                f"save reported success but no new backup appeared next to {sf.path}",
            )
        backup = max(after, key=lambda p: p.name)
        return SaveResult(
            saved_path=str(saved),
            backup_path=str(backup),
            integrity=self._integrity_info(sf),
        )

    # -- internals ---------------------------------------------------------

    def _require_open(self) -> SaveFile:
        """Return the live SaveFile or raise SAVE_NOT_OPEN."""
        if self._savefile is None:
            raise ApiError(ApiErrorCode.SAVE_NOT_OPEN, "no save is open")
        return self._savefile

    def _dry_run_scratch(self) -> SaveFile:
        """SaveFile over a copy of the current buffer, for validation only."""
        sf = self._require_open()
        return SaveFile(
            path=sf.path,
            data=bytearray(sf.data),
            layout=sf.layout,
            hash_scheme=sf.hash_scheme,
        )

    def _applied_not_saved(self, sf: SaveFile) -> bool:
        """Byte-compare in-memory buffer vs the file on disk.

        An unreadable disk file counts as different: the buffer holds state
        the disk can no longer confirm.
        """
        try:
            on_disk = sf.path.read_bytes()
        except OSError:
            return True
        return bytes(sf.data) != on_disk

    def _staged_info(self, sf: SaveFile) -> StagedInfo:
        entries: List[StagedEntry] = []
        if self._staged_money is not None:
            have_money = sf.get_money()
            if self._staged_money != have_money:
                entries.append(
                    StagedEntry(
                        field="money",
                        slot_index=None,
                        have=have_money,
                        want=self._staged_money,
                    )
                )
        for slot in sorted(self._staged_heat):
            try:
                have_heat = float(sf.get_slot_heat(slot))
            except ValueError:
                have_heat = float("nan")
            want = self._staged_heat[slot]
            if not math.isfinite(have_heat) or want != have_heat:
                entries.append(
                    StagedEntry(
                        field="slot_heat",
                        slot_index=slot,
                        have=have_heat if math.isfinite(have_heat) else 0.0,
                        want=want,
                    )
                )
        return StagedInfo(
            dirty=bool(entries),
            applied_not_saved=self._applied_not_saved(sf),
            entries=entries,
        )

    def _integrity_info(self, sf: SaveFile) -> IntegrityInfo:
        status = sf.validate_integrity()

        def verdict(name: str, ok: Optional[bool]) -> Optional[str]:
            if ok is None:
                return None
            return f"{name} {'OK' if ok else 'BAD'}"

        parts = [
            verdict("MD5", status.md5_ok),
            verdict("CRC1", status.crc_block1_ok),
            verdict("CRCdata", status.crc_data_ok),
            verdict("CRC2", status.crc_block2_ok),
            verdict("size", status.file_size_ok),
        ]
        summary = ", ".join(p for p in parts if p) or "no checks ran"
        return IntegrityInfo(
            hash_scheme=status.hash_scheme,
            md5_ok=status.md5_ok,
            crc_block1_ok=status.crc_block1_ok,
            crc_data_ok=status.crc_data_ok,
            crc_block2_ok=status.crc_block2_ok,
            file_size_ok=status.file_size_ok,
            summary=summary,
        )
