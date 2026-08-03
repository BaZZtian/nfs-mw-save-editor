"""One shared way to count Rap Sheet totals: bounty, escapes, busts.

The game's lifetime totals aggregate live garage records PLUS the sold-car
history block (engine trio FEPlayerCarDB::GetTotalBounty /
GetTotalEvadedPursuits / GetTotalBustedPursuits; sold-history summing is
verified by bytes for bounty and is a model inference for the two pursuit
counters — the corpus shows the counters accumulate exactly alongside
SoldHistoryBounty). Every page must use this module so Profile and Career can
never disagree again.
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
    """

    if len(data) != EXPECTED_SAVE_SIZE:
        return None
    live_bounty = live_escapes = live_busts = 0
    for k in range(GARAGE_RECORD_COUNT):
        base = GARAGE_RECORDS_OFFSET + k * GARAGE_RECORD_SIZE
        raw = bytes(data[base:base + GARAGE_RECORD_SIZE])
        if not is_live_garage_record(raw, k):
            continue
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
