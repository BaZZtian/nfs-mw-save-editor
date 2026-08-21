"""Typed contract models for the web-UI boundary.

Single source of truth for everything that crosses the wire. TypeScript
types in the web repo are generated from the JSON Schema this module dumps;
the schema's sha256 travels with the generated file as the drift detector.

Wire naming: camelCase on the wire, snake_case in Python. The mapping is
defined once, here, by the alias generator on `ApiModel`; nothing else may
rename fields.

Run `python -m nfs_mw_save_editor.api.schema` to print the combined JSON
Schema (deterministic key order) followed by its sha256 hex digest.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    """Base model with camelCase aliases, unknown-field rejection, and
    strict (no-coercion) validation: `"123"` is not a money value. Ints
    remain valid floats because JSON has one number type."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class ApiErrorCode(str, Enum):
    """Typed error classes carried in JSON-RPC error responses.

    INVALID_VALUE = the value can never be valid for this field (wrong
    range/type/shape). BLOCKED = the value is well-formed but the current
    save state refuses it (e.g. heat above the story cap); the message
    carries the core's own reason text verbatim.
    """

    SAVE_NOT_OPEN = "SAVE_NOT_OPEN"
    ALREADY_OPEN = "ALREADY_OPEN"
    INVALID_VALUE = "INVALID_VALUE"
    BLOCKED = "BLOCKED"
    IO_ERROR = "IO_ERROR"
    INTERNAL = "INTERNAL"


# JSON-RPC error `code` integers, one per ApiErrorCode. Negative values in
# the implementation-defined range, stable across releases.
JSONRPC_ERROR_CODES: Dict[ApiErrorCode, int] = {
    ApiErrorCode.SAVE_NOT_OPEN: -32001,
    ApiErrorCode.ALREADY_OPEN: -32002,
    ApiErrorCode.INVALID_VALUE: -32003,
    ApiErrorCode.BLOCKED: -32004,
    ApiErrorCode.IO_ERROR: -32005,
    ApiErrorCode.INTERNAL: -32006,
}


class RapSheet(ApiModel):
    """Aggregates from core `get_rap_sheet_totals()` (live + sold history)."""

    total_bounty: int
    escapes: int
    busts: int


class GarageCar(ApiModel):
    """One occupied career-linked garage slot, from `get_garage_slots()`."""

    slot_index: int = Field(description="career_slot of the pursuit record")
    model_name: str = Field(description="resolved display name from core")
    bounty: int
    heat: Optional[float] = Field(
        description="stored heat float; None when non-finite (JSON cannot "
        "carry NaN/inf, and the core fails closed on such values anyway)"
    )
    heat_level: Optional[int] = Field(
        description="whole heat level 1..5, None when the float is unreadable "
        "(core fails closed; the UI must show unknown, not reconstruct)"
    )
    heat_cap: int = Field(
        description="current story heat cap from get_story_heat_cap(); "
        "duplicated per car so the renderer needs no cross-lookups"
    )
    source: str = Field(
        description="verbatim SaveFile.derive_source_kind value: "
        "'My Cars' | 'Career' | 'Pink Slip' | 'Unknown' | 'Unknown (0xNN)'"
    )


class StagedEntry(ApiModel):
    """One staged (not yet applied) edit, have -> want."""

    field: Literal["money", "slot_heat"]
    slot_index: Optional[int] = Field(
        default=None, description="present only for slot_heat"
    )
    have: Union[int, float]
    want: Union[int, float]


class StagedInfo(ApiModel):
    """Staged-workflow status, mirrors the Qt badge semantics exactly.

    dirty = at least one staged entry exists (Qt: 'Unsaved changes').
    applied_not_saved = the in-memory buffer differs from the file on disk
    (Qt: 'Applied, not saved'), computed by byte comparison, never by
    bookkeeping flags.
    """

    dirty: bool
    applied_not_saved: bool
    entries: List[StagedEntry]


class IntegrityInfo(ApiModel):
    """Condensed core IntegrityStatus: verdicts and a human summary only.

    Raw digests/offsets stay behind the boundary; the UI never needs them.
    """

    hash_scheme: Optional[str]
    md5_ok: Optional[bool]
    crc_block1_ok: Optional[bool]
    crc_data_ok: Optional[bool]
    crc_block2_ok: Optional[bool]
    file_size_ok: bool
    summary: str = Field(description="one-line human verdict, e.g. 'MD5 OK, CRCs OK'")


class SaveState(ApiModel):
    """The single whole-truth state model; every mutation returns it.

    When `opened` is False every optional field is None and lists are
    empty; the frontend renders the empty state from this same shape.
    """

    opened: bool
    path: Optional[str]
    alias: Optional[str]
    money: Optional[int]
    rap_sheet: Optional[RapSheet]
    garage: List[GarageCar]
    staged: StagedInfo
    integrity: Optional[IntegrityInfo]
    warnings: List[str] = Field(
        description="non-fatal notices (e.g. garage detection degraded); "
        "empty list when clean"
    )


class OpenSaveParams(ApiModel):
    path: str


class SetMoneyParams(ApiModel):
    """Bound mirrors both the Qt editor (_parse_u32_text) and the core
    setter (_require_u32): full unsigned 32-bit range."""

    value: int = Field(ge=0, le=0xFFFFFFFF)


class SetSlotHeatParams(ApiModel):
    slot_index: int = Field(ge=0)
    value: float


class SaveResult(ApiModel):
    """Result of saveWithBackup: where things landed plus fresh integrity."""

    saved_path: str
    backup_path: str
    integrity: IntegrityInfo


class HelloResult(ApiModel):
    """Handshake payload with protocol version and server executable path."""

    protocol_version: str
    python_exe: str


#: Public contract models in deterministic wire-schema order.
CONTRACT_MODELS = [
    RapSheet,
    GarageCar,
    StagedEntry,
    StagedInfo,
    IntegrityInfo,
    SaveState,
    OpenSaveParams,
    SetMoneyParams,
    SetSlotHeatParams,
    SaveResult,
    HelloResult,
]


def dump_schema() -> str:
    """Return the combined JSON Schema for CONTRACT_MODELS as a string.

    Deterministic: models in CONTRACT_MODELS order, keys sorted, no
    whitespace variance; the sha256 of this exact string is the contract
    fingerprint the web repo pins.
    """
    import json

    from . import PROTOCOL_VERSION

    combined = {"protocolVersion": PROTOCOL_VERSION}
    for model in CONTRACT_MODELS:
        combined[model.__name__] = model.model_json_schema(by_alias=True)
    return json.dumps(combined, sort_keys=True, indent=2)


def schema_sha256() -> str:
    """sha256 hex digest of dump_schema()."""
    import hashlib

    return hashlib.sha256(dump_schema().encode("utf-8")).hexdigest()


if __name__ == "__main__":
    print(dump_schema())
    print(schema_sha256())
