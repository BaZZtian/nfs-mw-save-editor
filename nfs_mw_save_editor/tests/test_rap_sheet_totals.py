from __future__ import annotations

import struct

from core import garage_records
from core.rap_sheet_totals import RapSheetTotals, read_rap_sheet_totals


def _blank_save() -> bytearray:
    """Zero-filled save-sized buffer with every garage slot marked empty."""

    data = bytearray(garage_records.EXPECTED_SAVE_SIZE)
    for k in range(garage_records.GARAGE_RECORD_COUNT):
        data[garage_records.GARAGE_RECORDS_OFFSET + k * garage_records.GARAGE_RECORD_SIZE] = (
            garage_records.GARAGE_EMPTY_HANDLE
        )
    return data


def _write_live_record(
    data: bytearray, index: int, *, bounty: int, escaped: int, busted: int
) -> None:
    base = garage_records.GARAGE_RECORDS_OFFSET + index * garage_records.GARAGE_RECORD_SIZE
    data[base:base + garage_records.GARAGE_RECORD_SIZE] = b"\x00" * garage_records.GARAGE_RECORD_SIZE
    data[base] = index
    data[base + 1] = 0xCD
    data[base + 0x0A:base + 0x0C] = b"\xCD\xCD"
    struct.pack_into("<I", data, base + garage_records.GARAGE_RECORD_BOUNTY_REL, bounty)
    struct.pack_into("<H", data, base + garage_records.GARAGE_RECORD_ESCAPED_REL, escaped)
    struct.pack_into("<H", data, base + garage_records.GARAGE_RECORD_BUSTED_REL, busted)


def _write_sold_history(data: bytearray, *, bounty: int, escapes: int, busts: int) -> None:
    struct.pack_into("<I", data, garage_records.SOLD_HISTORY_BOUNTY_OFFSET, bounty)
    struct.pack_into("<H", data, garage_records.SOLD_HISTORY_EVADED_OFFSET, escapes)
    struct.pack_into("<H", data, garage_records.SOLD_HISTORY_BUSTED_OFFSET, busts)


def test_totals_sum_live_records_and_sold_history() -> None:
    """Assert both components land in the right fields and totals add them."""

    data = _blank_save()
    _write_live_record(data, 0, bounty=100_000, escaped=7, busted=1)
    _write_live_record(data, 4, bounty=250_000, escaped=3, busted=0)
    _write_sold_history(data, bounty=50_000, escapes=12, busts=2)

    totals = read_rap_sheet_totals(bytes(data))
    assert totals == RapSheetTotals(
        live_bounty=350_000,
        live_escapes=10,
        live_busts=1,
        sold_bounty=50_000,
        sold_escapes=12,
        sold_busts=2,
    )
    assert totals.total_bounty == 400_000
    assert totals.total_escapes == 22
    assert totals.total_busts == 3


def test_stale_payload_under_empty_handle_is_ignored() -> None:
    """Assert a sold-car payload parked under Handle 0xFF adds nothing."""

    data = _blank_save()
    _write_live_record(data, 2, bounty=90_000, escaped=5, busted=0)
    # Stale record: full live-looking payload, then the handle freed to 0xFF.
    _write_live_record(data, 3, bounty=777_777, escaped=99, busted=9)
    data[garage_records.GARAGE_RECORDS_OFFSET + 3 * garage_records.GARAGE_RECORD_SIZE] = (
        garage_records.GARAGE_EMPTY_HANDLE
    )

    totals = read_rap_sheet_totals(bytes(data))
    assert (totals.live_bounty, totals.live_escapes, totals.live_busts) == (90_000, 5, 0)


def test_sold_history_alone_carries_the_totals() -> None:
    """Assert a zero-car garage still reports the sold-history lifetime stats."""

    data = _blank_save()
    _write_sold_history(data, bounty=61_821_320, escapes=102, busts=0)

    totals = read_rap_sheet_totals(bytes(data))
    assert (totals.live_bounty, totals.live_escapes, totals.live_busts) == (0, 0, 0)
    assert totals.total_bounty == 61_821_320
    assert totals.total_escapes == 102
    assert totals.total_busts == 0


def test_non_save_buffer_returns_none() -> None:
    """Assert the reader fails closed on a wrong-sized buffer."""

    assert read_rap_sheet_totals(b"\x00" * 100) is None
    assert read_rap_sheet_totals(bytes(garage_records.EXPECTED_SAVE_SIZE - 1)) is None
