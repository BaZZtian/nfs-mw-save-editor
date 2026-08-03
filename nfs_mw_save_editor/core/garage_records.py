"""Native garage-record (engine FECareerRecord) layout and occupancy rules.

The save stores a fixed FEPlayerCarDB.CareerRecords[25] array serialized
whole. Occupancy is decided by the Handle byte at +0x00 alone:

- Handle == 0xFF        -> empty slot. The rest of the payload is whatever
                           bytes were there before (uninitialized fill or a
                           stale sold-car record) and is invisible to the game.
- Handle == slot index  -> live record.

Any other Handle value is unexplained data and must be rejected (never
observed across the 721-save corpus). Live records additionally must pass the
canonical pad-byte gate below; that is the editor's extra fail-closed policy,
not native semantics. MaxBusted/TimesBusted are real gameplay fields
(impound strikes), never detection criteria.

Shared by savefile.py and career_transplant.py so the occupancy rule exists
in exactly one place.
"""

GARAGE_RECORDS_OFFSET = 0xE2ED
GARAGE_RECORD_SIZE = 0x38
GARAGE_RECORD_COUNT = 25
GARAGE_EMPTY_HANDLE = 0xFF


def has_canonical_pad_bytes(raw: bytes) -> bool:
    """Pad/alignment bytes of a healthy serialized FECareerRecord.

    +0x01 pad 0xCD, +0x07 Pad1 0x00, +0x08..09 Pad2 0x0000,
    +0x0A..0B struct alignment fill 0xCDCD.
    """

    return (
        len(raw) == GARAGE_RECORD_SIZE
        and raw[1] == 0xCD
        and raw[7] == 0x00
        and raw[8:10] == b"\x00\x00"
        and raw[10:12] == b"\xCD\xCD"
    )


def is_empty_garage_record(raw: bytes) -> bool:
    return len(raw) == GARAGE_RECORD_SIZE and raw[0] == GARAGE_EMPTY_HANDLE


def is_live_garage_record(raw: bytes, slot_index: int) -> bool:
    return (
        len(raw) == GARAGE_RECORD_SIZE
        and raw[0] == int(slot_index)
        and has_canonical_pad_bytes(raw)
    )
