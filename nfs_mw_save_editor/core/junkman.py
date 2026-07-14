from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Slot:
    index: int
    abs_off: int
    type_id: int
    count: int
    raw: bytes


class JunkmanInventory:
    """
    Slot-based Junkman inventory (1 token = 1 slot).
    Base and slot_count are auto-detected per save.

    Engine truth (FEMarkerManager::OwnedMarkers[63], PS2 debug symbols,
    layout confirmed on PC v1.3): each 12-byte slot is
    struct OwnedMarker { ePossibleMarker Marker; int Param; eMarkerStates State; }
    Marker is 1..21 (MARKER_LAST = 21); Param is always 0 for inventoried
    markers (pink slips / cash carry a param but are consumed instantly at
    the marker-select screen, so they never reach this array organically).
    The +8 field is DECLARED as eMarkerStates (0 NOT_OWNED / 1 OWNED /
    2 USED), but the PC frontend evidently sums it when counting tokens:
    writing N there shows as N tokens in game (confirmed by in-game testing).
    The game itself only ever writes 0/1 here (one slot per token), which
    is also what this editor does - both representations display the same.
    """

    SAVED_DATA_START = 0x34  # fixed for PC v1.3 header
    SLOT_STRIDE = 0x0C
    SLOT_SIZE = 0x0C
    # Engine ground truth: FEMarkerManager::OwnedMarkers[63] lives at a fixed
    # position in the PC v1.3 save - absolute 0x5739, i.e. 0x5705 relative to
    # saved_data. The old heuristic scan (longest run of slot-like records)
    # mis-anchored on saves carrying hand-written ghost slots from the early
    # token experiments (state bytes > 1 broke the run), silently hiding real
    # tokens. The belt is a fixed struct; treat it as one.
    BASE_REL = 0x5705
    SLOT_COUNT = 63

    def __init__(self, savefile: "SaveFile"):
        self.sf = savefile
        self.data = savefile.data
        saved_start, saved_end = self.sf.saved_data_slice()
        if saved_start + self.BASE_REL + self.SLOT_COUNT * self.SLOT_STRIDE > saved_end:
            raise ValueError("Junkman slot array out of range for this file")
        self.base_rel: int = self.BASE_REL
        self.base_abs: int = saved_start + self.BASE_REL
        self.slot_count: int = self.SLOT_COUNT

    # ---- core helpers ----
    def slot_abs(self, index: int) -> int:
        if index < 0 or index >= self.slot_count:
            raise IndexError(f"Slot index {index} out of bounds (0..{self.slot_count - 1})")
        return self.base_abs + index * self.SLOT_STRIDE

    @staticmethod
    def is_empty_slot(raw12: bytes) -> bool:
        return len(raw12) == 12 and raw12 == b"\x00" * 12

    # ---- IO ----
    def read_slot(self, index: int) -> Slot:
        abs_off = self.slot_abs(index)
        raw = bytes(self.data[abs_off : abs_off + self.SLOT_SIZE])
        if len(raw) != self.SLOT_SIZE:
            raise IndexError("Slot read out of bounds")
        type_id = raw[0]
        count = raw[8]
        return Slot(index=index, abs_off=abs_off, type_id=type_id, count=count, raw=raw)

    def read_slots(self) -> List[Slot]:
        return [self.read_slot(i) for i in range(self.slot_count)]

    def _write_full_slot(self, abs_off: int, type_id: int) -> None:
        payload = bytearray(self.SLOT_SIZE)
        payload[0] = type_id & 0xFF
        payload[8] = 1  # Count always 1 for filled slot
        self.data[abs_off : abs_off + self.SLOT_SIZE] = payload

    def _clear_slot(self, abs_off: int) -> None:
        self.data[abs_off : abs_off + self.SLOT_SIZE] = b"\x00" * self.SLOT_SIZE

    # ---- model operations ----
    def get_counts(self) -> Dict[int, int]:
        counts: Dict[int, int] = {}
        for slot in self.read_slots():
            # +0x08 is eMarkerStates; only OWNED (1) markers are available
            # (0 = not owned, 2 = used).
            if slot.type_id == 0 or slot.count != 1:
                continue
            counts[slot.type_id] = counts.get(slot.type_id, 0) + 1
        return counts

    def free_slots(self) -> int:
        return sum(1 for s in self.read_slots() if self.is_empty_slot(s.raw))

    def apply_counts(self, desired: Dict[int, int], clamp_max: int = 63) -> None:
        """
        Apply counts transactionally using one-slot-per-token.
        - Preserve unknown IDs (from current save) not present in desired.
        - Ensure total tokens fit in slot_count.
        - Clear all slots, then rewrite sequentially.
        """
        have = self.get_counts()
        # preserve unspecified
        want_full = dict(have)
        for k, v in desired.items():
            want_full[int(k)] = int(v)
        # clamp to allowed range
        for k in list(want_full.keys()):
            want_full[k] = max(0, min(want_full[k], clamp_max))

        needed = sum(v for v in want_full.values() if v > 0)
        if needed > self.slot_count:
            raise ValueError(f"Need {needed} slots, have {self.slot_count}")

        # clear all slots
        for s in self.read_slots():
            self._clear_slot(s.abs_off)

        # write tokens sequentially
        idx = 0
        for tid in sorted(want_full.keys()):
            cnt = want_full[tid]
            for _ in range(cnt):
                if idx >= self.slot_count:
                    raise ValueError("Internal error: slot overflow")
                self._write_full_slot(self.slot_abs(idx), tid)
                idx += 1

    def clear_all(self) -> None:
        for s in self.read_slots():
            self._clear_slot(s.abs_off)
