"""One shared way to count Rap Sheet totals: bounty, escapes, busts.

The game's lifetime totals aggregate live garage records and the sold-car
history block. Sold bounty is verified by bytes; sold escape and bust totals
follow the corresponding engine aggregation model. All UI consumers use this
module so displayed totals share one rule.
"""

from dataclasses import dataclass
from typing import Optional

from core.garage_records import (
    EXPECTED_SAVE_SIZE,
    GARAGE_RECORD_BOUNTY_REL,
    GARAGE_RECORD_BUSTED_REL,
    GARAGE_RECORD_COUNT,
    GARAGE_RECORD_ESCAPED_REL,
    GARAGE_RECORD_SIZE,
    GARAGE_RECORDS_OFFSET,
    SOLD_HISTORY_BOUNTY_OFFSET,
    SOLD_HISTORY_BUSTED_OFFSET,
    SOLD_HISTORY_EVADED_OFFSET,
    is_empty_garage_record,
    is_live_garage_record,
)


@dataclass(frozen=True)
class RapSheetTotals:
    """Live-garage and sold-history components of the Rap Sheet aggregates."""

    live_bounty: int
    live_escapes: int
    live_busts: int
    sold_bounty: int
    sold_escapes: int
    sold_busts: int

    @property
    def total_bounty(self) -> int:
        return self.live_bounty + self.sold_bounty

    @property
    def total_escapes(self) -> int:
        return self.live_escapes + self.sold_escapes

    @property
    def total_busts(self) -> int:
        return self.live_busts + self.sold_busts


def read_rap_sheet_totals(data: bytes) -> Optional[RapSheetTotals]:
    """Read both aggregate components from one save snapshot.

    Returns None when the buffer is not a save. Empty garage slots (stale
    payloads included) are skipped via the shared Handle-based occupancy rule.
    A record that is neither empty nor canonically live raises ValueError;
    same fail-closed rule as SaveFile.get_pursuit_records; an aggregate over
    unexplained records would silently under-count.
    """

    if len(data) != EXPECTED_SAVE_SIZE:
        return None
    live_bounty = live_escapes = live_busts = 0
    for k in range(GARAGE_RECORD_COUNT):
        base = GARAGE_RECORDS_OFFSET + k * GARAGE_RECORD_SIZE
        raw = bytes(data[base:base + GARAGE_RECORD_SIZE])
        if is_empty_garage_record(raw):
            continue
        if not is_live_garage_record(raw, k):
            if raw[0] != k:
                raise ValueError(
                    f"Garage record {k} has unexpected handle 0x{raw[0]:02X}"
                )
            raise ValueError(
                f"Garage record {k} fails the canonical pad-byte gate"
            )
        live_bounty += int.from_bytes(
            raw[GARAGE_RECORD_BOUNTY_REL:GARAGE_RECORD_BOUNTY_REL + 4], "little"
        )
        live_escapes += int.from_bytes(
            raw[GARAGE_RECORD_ESCAPED_REL:GARAGE_RECORD_ESCAPED_REL + 2], "little"
        )
        live_busts += int.from_bytes(
            raw[GARAGE_RECORD_BUSTED_REL:GARAGE_RECORD_BUSTED_REL + 2], "little"
        )
    return RapSheetTotals(
        live_bounty=live_bounty,
        live_escapes=live_escapes,
        live_busts=live_busts,
        sold_bounty=int.from_bytes(
            data[SOLD_HISTORY_BOUNTY_OFFSET:SOLD_HISTORY_BOUNTY_OFFSET + 4], "little"
        ),
        sold_escapes=int.from_bytes(
            data[SOLD_HISTORY_EVADED_OFFSET:SOLD_HISTORY_EVADED_OFFSET + 2], "little"
        ),
        sold_busts=int.from_bytes(
            data[SOLD_HISTORY_BUSTED_OFFSET:SOLD_HISTORY_BUSTED_OFFSET + 2], "little"
        ),
    )
