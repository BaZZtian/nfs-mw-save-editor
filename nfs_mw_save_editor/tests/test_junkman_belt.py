"""Junkman token belt: fixed engine location, ghost-slot tolerance.

The belt is FEMarkerManager::OwnedMarkers[63] at absolute 0x5739 (0x5705
relative to saved_data) in the PC v1.3 save. Ghost slots with state bytes
greater than one ensure parsing does not depend on a slot-like-record scan.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.junkman import JunkmanInventory

SAVE_SIZE = 63596
MD5_LEN = 16
BELT_ABS = 0x5739


class _StubSave:
    """Minimal SaveFile stand-in for JunkmanInventory."""

    def __init__(self, data: bytearray):
        self.data = data

    def saved_data_slice(self):
        return JunkmanInventory.SAVED_DATA_START, len(self.data) - MD5_LEN

    def saved_data(self) -> bytes:
        s, e = self.saved_data_slice()
        return bytes(self.data[s:e])


def _write_slot(data: bytearray, index: int, type_id: int, state: int, param: int = 0):
    struct.pack_into("<iii", data, BELT_ABS + index * 12, type_id, param, state)


def _make_save_with_ghost() -> bytearray:
    data = bytearray(SAVE_SIZE)
    # Real tokens preceding the ghost must remain visible.
    _write_slot(data, 0, 17, 1)
    _write_slot(data, 1, 17, 1)
    _write_slot(data, 2, 17, 1)
    _write_slot(data, 3, 20, 1)
    _write_slot(data, 4, 4, 1)
    _write_slot(data, 5, 0, 2)   # ghost: type 0, state USED - broke the scan
    _write_slot(data, 6, 2, 1)
    _write_slot(data, 7, 25, 1)  # experiment junk: nonexistent type
    return data


def test_belt_is_anchored_at_engine_offset():
    inv = JunkmanInventory(_StubSave(_make_save_with_ghost()))
    assert inv.base_abs == BELT_ABS
    assert inv.base_rel == 0x5705
    assert inv.slot_count == 63


def test_tokens_before_ghost_are_visible():
    inv = JunkmanInventory(_StubSave(_make_save_with_ghost()))
    counts = inv.get_counts()
    assert counts[17] == 3
    assert counts[20] == 1
    assert counts[4] == 1
    assert counts[2] == 1
    assert counts[25] == 1     # junk is read (preserve/clear decides its fate)
    assert 0 not in counts     # ghost slot contributes nothing


def test_apply_counts_heals_ghost_and_can_drop_junk():
    stub = _StubSave(_make_save_with_ghost())
    inv = JunkmanInventory(stub)
    inv.apply_counts({25: 0})  # drop junk, keep everything else
    counts = inv.get_counts()
    assert counts == {17: 3, 20: 1, 4: 1, 2: 1}
    # Belt fully normalized: ghost wiped, tokens packed from slot 0.
    for index in range(63):
        raw = bytes(stub.data[BELT_ABS + index * 12: BELT_ABS + (index + 1) * 12])
        if index < 6:
            assert raw[0] != 0 and raw[8] == 1
        else:
            assert raw == b"\x00" * 12


def test_belt_rejects_truncated_file():
    import pytest
    with pytest.raises(ValueError):
        JunkmanInventory(_StubSave(bytearray(0x2000)))
