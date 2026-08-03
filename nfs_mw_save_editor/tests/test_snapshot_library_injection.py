from pathlib import Path
from dataclasses import replace
import json
import struct
import sys
import tempfile
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from core.models import (
    CareerSlotStatus,
    FullCarBuildSnapshot,
    OwnedCarRecord,
    OwnedCarSlotStatus,
    OwnedCarTemplate,
    PartsSlotStatus,
    SnapshotLibraryEntry,
    SnapshotVisualSidecarEntry,
    VisualSidecarTemplate,
)
from core.savefile import SaveFile


def _normalized_block(seed: int = 0) -> bytes:
    block = bytearray((seed + index) & 0xFF for index in range(SaveFile.PARTS_BLOCK_SIZE))
    block[SaveFile.PARTS_MARKER_OFFSET:SaveFile.PARTS_MARKER_OFFSET + 4] = b"\x00\x00\x00\x00"
    return bytes(block)


def _block_with_marker(normalized_block: bytes, marker: bytes) -> bytes:
    block = bytearray(normalized_block)
    block[SaveFile.PARTS_MARKER_OFFSET:SaveFile.PARTS_MARKER_OFFSET + 4] = marker
    return bytes(block)


def _snapshot_json_payload(
    *,
    display_name: str,
    kind: str = SaveFile.SNAPSHOT_KIND,
    source_kind: str = "Career",
    location_bits: int = SaveFile.CAREER_FLAG,
    signature: bytes = b"\x11" * 8,
    normalized_block: bytes | None = None,
    sidecar_block: bytes | None = None,
) -> dict:
    block = normalized_block if normalized_block is not None else _normalized_block(0x10)
    payload = {
        "kind": kind,
        "source_file": "fixture-save",
        "display_name": display_name,
        "source_kind": source_kind,
        "primary_owned_record_template": {
            "car_number": 123,
            "signature_hex": SaveFile._bytes_to_hex(signature),
            "location_bits": location_bits,
            "misc_bits": 9,
            "source_kind": source_kind,
        },
        "primary_build_block": {
            "normalized_hex": SaveFile._bytes_to_hex(block),
            "performance_levels": {
                "Tires": 2,
                "Brakes": 1,
            },
            "primary_visual_fields": {
                "Paint": "05",
                "Body Vinyl": "01 00",
            },
        },
        "requires_unresolved_global_visual_state": False,
        "global_visual_table": {
            "uniform_value": 1,
            "mode_offset": SaveFile.VISUAL_TABLE_MODE_OFFSET,
            "mode_uniform_value": 1,
            "mode_tail_value": None,
        },
    }
    if sidecar_block is not None:
        payload["optional_visual_sidecar"] = {
            "owned_record_signature_clone_hex": SaveFile._bytes_to_hex(signature),
            "owned_record_location_bits": SaveFile.MY_CARS_FLAG,
            "owned_record_misc_bits": 12,
            "sidecar_parts_slot_offset": 1,
            "normalized_sidecar_build_block_hex": SaveFile._bytes_to_hex(sidecar_block),
            "sidecar_marker_hex": SaveFile._bytes_to_hex(SaveFile.EMPTY_PARTS_BLOCK_MARKER),
        }
    return payload


def _write_snapshot_json(path: Path, **kwargs) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_snapshot_json_payload(**kwargs), indent=2), encoding="utf-8")
    return path


def _write_raw_snapshot_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _make_snapshot(
    *,
    snapshot_id: str = "test-snapshot",
    display_name: str = "Fixture Car",
    source_kind: str = "Career",
    location_bits: int = SaveFile.CAREER_FLAG,
    misc_bits: int = 9,
    signature: bytes = b"\x22" * 8,
    normalized_block: bytes | None = None,
    requires_unresolved_global_visual_state: bool = False,
    sidecar_offset: int | None = None,
    sidecar_block: bytes | None = None,
) -> SnapshotLibraryEntry:
    sidecar = None
    has_sidecar = sidecar_offset is not None
    if has_sidecar:
        sidecar = SnapshotVisualSidecarEntry(
            owned_record_signature_clone=signature,
            owned_record_location_bits=SaveFile.MY_CARS_FLAG,
            owned_record_misc_bits=12,
            sidecar_parts_slot_offset=int(sidecar_offset),
            normalized_sidecar_build_block=sidecar_block or _normalized_block(0x80),
            sidecar_marker=SaveFile.EMPTY_PARTS_BLOCK_MARKER,
        )
    return SnapshotLibraryEntry(
        snapshot_id=snapshot_id,
        json_path=Path(f"{snapshot_id}.json"),
        library_bucket="Main",
        file_label=snapshot_id,
        display_name=display_name,
        source_file="fixture-save",
        source_kind=source_kind,
        primary_owned_record_template=OwnedCarTemplate(
            car_number=0,
            signature=signature,
            location_bits=location_bits,
            misc_bits=misc_bits,
            source_kind=source_kind,
        ),
        normalized_primary_build_block=normalized_block or _normalized_block(0x20),
        performance_levels=(),
        primary_visual_fields=(),
        requires_unresolved_global_visual_state=requires_unresolved_global_visual_state,
        has_visual_sidecar=has_sidecar,
        optional_visual_sidecar=sidecar,
    )


def _owned_slot(slot_index: int, *, reusable: bool = True, abs_off: int | None = None) -> OwnedCarSlotStatus:
    slot_abs_off = (
        SaveFile.CAREER_VEHICLE_BASE_OFFSET + slot_index * SaveFile.CAREER_VEHICLE_SIZE
        if abs_off is None
        else int(abs_off)
    )
    return OwnedCarSlotStatus(
        slot_index=slot_index,
        abs_off=slot_abs_off,
        occupied=not reusable,
        reusable=reusable,
        blocked_reason=None,
        status_kind="reusable" if reusable else "occupied",
        status_code="reusable" if reusable else "occupied",
        status_detail=None,
        car_number=SaveFile.EMPTY_CAR_NUMBER if reusable else slot_index + 1,
        location_bits=0,
        misc_bits=0,
        parts_slot=SaveFile.EMPTY_CAREER_SLOT,
        career_slot=SaveFile.EMPTY_CAREER_SLOT,
    )


def _parts_abs_off(parts_slot: int) -> int:
    return SaveFile.PARTS_BLOCK_BASE_OFFSET + (
        int(parts_slot) - SaveFile.PARTS_BLOCK_SLOT_BASE
    ) * SaveFile.PARTS_BLOCK_SIZE


def _parts_slot(parts_slot: int, *, reusable: bool = True) -> PartsSlotStatus:
    return PartsSlotStatus(
        parts_slot=parts_slot,
        abs_off=_parts_abs_off(parts_slot),
        referenced_by_owned_car=not reusable,
        reusable=reusable,
        blocked_reason=None if reusable else "Referenced by owned-car record",
        status_kind="reusable" if reusable else "occupied",
        status_code="reusable" if reusable else "occupied_owned_reference",
        status_detail=None if reusable else "Referenced by owned-car record",
        marker=SaveFile.EMPTY_PARTS_BLOCK_MARKER,
    )


def _career_slot(career_slot: int, *, reusable: bool = True) -> CareerSlotStatus:
    return CareerSlotStatus(
        career_slot=career_slot,
        abs_off=SaveFile.GARAGE_BASE_OFFSET + career_slot * SaveFile.GARAGE_SLOT_SIZE,
        linked_car_count=0 if reusable else 1,
        reusable=reusable,
        blocked_reason=None if reusable else "occupied",
        status_kind="reusable" if reusable else "occupied",
        status_code="reusable" if reusable else "occupied",
        status_detail=None if reusable else "occupied",
        bounty=0,
        escaped=0,
        busted=0,
        is_zero=True,
    )


def _existing_record(car_number: int = 7) -> OwnedCarRecord:
    return OwnedCarRecord(
        car_number=car_number,
        signature=b"\x01" * 8,
        location_bits=SaveFile.MY_CARS_FLAG,
        misc_bits=0,
        parts_slot=40,
        career_slot=SaveFile.EMPTY_CAREER_SLOT,
        abs_off=SaveFile.CAREER_VEHICLE_BASE_OFFSET + 0x200,
    )


def _make_full_car_build_snapshot(*, with_sidecar: bool) -> FullCarBuildSnapshot:
    signature = b"\x31\x32\x33\x34\x35\x36\x37\x38"
    primary_block = _normalized_block(0x34)
    primary_raw = _block_with_marker(primary_block, b"\x2D\xCD\xCD\xCD")
    sidecar = None
    if with_sidecar:
        sidecar_block = _normalized_block(0x74)
        sidecar = VisualSidecarTemplate(
            owned_record_abs_off=SaveFile.CAREER_VEHICLE_BASE_OFFSET + SaveFile.CAREER_VEHICLE_SIZE,
            owned_record_signature_clone=signature,
            owned_record_location_bits=SaveFile.MY_CARS_FLAG,
            owned_record_misc_bits=12,
            sidecar_parts_slot_offset=1,
            sidecar_parts_slot=46,
            sidecar_block_abs_off=_parts_abs_off(46),
            owned_record_raw=b"\x00" * SaveFile.CAREER_VEHICLE_SIZE,
            sidecar_build_block=_block_with_marker(sidecar_block, SaveFile.EMPTY_PARTS_BLOCK_MARKER),
            normalized_sidecar_build_block=sidecar_block,
        )
    return FullCarBuildSnapshot(
        car_abs_off=SaveFile.CAREER_VEHICLE_BASE_OFFSET,
        display_name="Round Trip Car",
        source_kind="Pink Slip",
        car_number=88,
        signature=signature,
        location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
        misc_bits=9,
        parts_slot=45,
        career_slot=4,
        primary_owned_record_template=OwnedCarTemplate(
            car_number=88,
            signature=signature,
            location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
            misc_bits=9,
            source_kind="Pink Slip",
        ),
        primary_build_block_abs_off=_parts_abs_off(45),
        primary_build_block=primary_raw,
        normalized_primary_build_block=primary_block,
        performance_levels=(("Tires", 3), ("Engine", 4)),
        primary_visual_fields=(("Paint", "05"), ("Body Vinyl", "01 00")),
        optional_visual_sidecar=sidecar,
        requires_unresolved_global_visual_state=True,
        global_visual_table_entries=(b"\x01\xFF\xFF\xFF\x02\xFF\xFF\xFF",),
        global_visual_table_values=(1,),
        global_visual_table_uniform_value=1,
        global_visual_table_mode_offset=SaveFile.VISUAL_TABLE_MODE_OFFSET,
        global_visual_table_mode_values=(2,),
        global_visual_table_mode_uniform_value=2,
        global_visual_table_mode_tail_value=None,
    )


def _new_savefile_buffer() -> SaveFile:
    sf = object.__new__(SaveFile)
    sf.path = Path("fixture-save")
    sf.data = bytearray(b"\xEE" * (SaveFile.GARAGE_BASE_OFFSET + SaveFile.GARAGE_SLOT_SIZE * 2))
    # Empty garage slots with stale 0xEE payloads (Handle 0xFF is the only
    # thing that makes a slot empty; the rest is legal garbage).
    for slot in range(2):
        sf.data[SaveFile.GARAGE_BASE_OFFSET + slot * SaveFile.GARAGE_SLOT_SIZE] = SaveFile.GARAGE_EMPTY_HANDLE
    return sf


def _read_owned_record(raw: bytes) -> dict:
    return {
        "car_number": struct.unpack_from("<I", raw, 0x00)[0],
        "signature": raw[SaveFile.CAREER_VEHICLE_SIGNATURE_OFFSET:SaveFile.CAREER_VEHICLE_SIGNATURE_OFFSET + 8],
        "location_bits": struct.unpack_from("<H", raw, SaveFile.CAREER_VEHICLE_FLAGS_OFFSET)[0],
        "misc_bits": struct.unpack_from("<H", raw, SaveFile.CAREER_VEHICLE_FLAGS2_OFFSET)[0],
        "parts_slot": raw[SaveFile.CAREER_VEHICLE_PARTS_SLOT_OFFSET],
        "career_slot": raw[SaveFile.CAREER_VEHICLE_SLOT_OFFSET],
        "sentinel": raw[0x12:0x14],
    }


class SnapshotLibraryLoadingTests(unittest.TestCase):
    def test_load_snapshot_library_entry_parses_legacy_bonus_sidecar_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            root = Path(tmp_dir_text) / "library"
            block = _normalized_block(0x31)
            sidecar_block = _normalized_block(0x61)
            json_path = _write_snapshot_json(
                root / "bonus_cars" / "boss_car_snapshot_Test_Sidecar.json",
                display_name="Test Sidecar",
                kind=SaveFile.LEGACY_SNAPSHOT_KIND,
                source_kind="Pink Slip",
                location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
                normalized_block=block,
                sidecar_block=sidecar_block,
            )

            entry = SaveFile.load_snapshot_library_entry(json_path, library_root=root)

        self.assertEqual(entry.library_bucket, "Bonus")
        self.assertEqual(entry.display_name, "Test Sidecar")
        self.assertEqual(entry.source_kind, "Pink Slip")
        self.assertEqual(entry.primary_owned_record_template.location_bits, SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)
        self.assertEqual(entry.normalized_primary_build_block, block)
        self.assertIn(("Tires", 2), entry.performance_levels)
        self.assertIn(("Paint", "05"), entry.primary_visual_fields)
        self.assertTrue(entry.has_visual_sidecar)
        self.assertIsNotNone(entry.optional_visual_sidecar)
        self.assertEqual(entry.optional_visual_sidecar.sidecar_parts_slot_offset, 1)
        self.assertEqual(entry.optional_visual_sidecar.normalized_sidecar_build_block, sidecar_block)
        self.assertEqual(entry.optional_visual_sidecar.sidecar_marker, SaveFile.EMPTY_PARTS_BLOCK_MARKER)
        self.assertEqual(entry.global_visual_table_mode_offset, SaveFile.VISUAL_TABLE_MODE_OFFSET)
        self.assertEqual(entry.global_visual_table_mode_uniform_value, 1)

    def test_load_snapshot_library_orders_main_blacklist_then_bonus_then_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            tmp_dir = Path(tmp_dir_text)
            root = tmp_dir / "library"
            user_root = tmp_dir / "user_builds"
            _write_snapshot_json(
                root / "blacklist" / "boss_car_snapshot_VW_Golf_GTI.json",
                display_name="VW Golf GTI",
                kind=SaveFile.LEGACY_SNAPSHOT_KIND,
            )
            _write_snapshot_json(
                root / "blacklist" / "boss_car_snapshot_BMW_M3_GTR.json",
                display_name="BMW M3 GTR",
                kind=SaveFile.LEGACY_SNAPSHOT_KIND,
            )
            _write_snapshot_json(
                root / "bonus_cars" / "car_build_snapshot_Bonus_Car.json",
                display_name="Bonus Car",
            )
            _write_snapshot_json(
                user_root / "car_build_snapshot_User_Build.json",
                display_name="User Build",
            )

            entries = SaveFile.load_snapshot_library(root, user_root=user_root)

        self.assertEqual(
            [entry.display_name for entry in entries],
            ["BMW M3 GTR", "VW Golf GTI", "Bonus Car", "User Build"],
        )
        self.assertEqual(
            [entry.library_bucket for entry in entries],
            ["Main", "Main", "Bonus", "User"],
        )


class SnapshotLibraryLoadingErrorTests(unittest.TestCase):
    def test_load_snapshot_library_entry_rejects_unknown_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            path = Path(tmp_dir_text) / "car_build_snapshot_Bad_Kind.json"
            payload = _snapshot_json_payload(display_name="Bad Kind", kind="unknown_snapshot_kind")
            _write_raw_snapshot_json(path, payload)

            with self.assertRaises(ValueError) as caught:
                SaveFile.load_snapshot_library_entry(path, library_root=Path(tmp_dir_text))

        self.assertIn(
            f"is not a {SaveFile.SNAPSHOT_KIND} or {SaveFile.LEGACY_SNAPSHOT_KIND} file",
            str(caught.exception),
        )

    def test_load_snapshot_library_entry_rejects_invalid_primary_block_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            path = Path(tmp_dir_text) / "car_build_snapshot_Bad_Primary_Block.json"
            payload = _snapshot_json_payload(display_name="Bad Primary Block")
            payload["primary_build_block"]["normalized_hex"] = SaveFile._bytes_to_hex(
                b"\xAA" * (SaveFile.PARTS_BLOCK_SIZE - 1)
            )
            _write_raw_snapshot_json(path, payload)

            with self.assertRaises(ValueError) as caught:
                SaveFile.load_snapshot_library_entry(path, library_root=Path(tmp_dir_text))

        self.assertIn(
            f"has invalid normalized primary block size {SaveFile.PARTS_BLOCK_SIZE - 1}",
            str(caught.exception),
        )

    def test_load_snapshot_library_entry_rejects_invalid_primary_signature_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            path = Path(tmp_dir_text) / "car_build_snapshot_Bad_Primary_Signature.json"
            payload = _snapshot_json_payload(display_name="Bad Primary Signature")
            payload["primary_owned_record_template"]["signature_hex"] = SaveFile._bytes_to_hex(b"\xAA" * 7)
            _write_raw_snapshot_json(path, payload)

            with self.assertRaises(ValueError) as caught:
                SaveFile.load_snapshot_library_entry(path, library_root=Path(tmp_dir_text))

        self.assertIn("has invalid signature length 7", str(caught.exception))

    def test_load_snapshot_library_entry_rejects_invalid_sidecar_block_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            path = Path(tmp_dir_text) / "car_build_snapshot_Bad_Sidecar_Block.json"
            payload = _snapshot_json_payload(display_name="Bad Sidecar Block", sidecar_block=_normalized_block(0x51))
            payload["optional_visual_sidecar"]["normalized_sidecar_build_block_hex"] = SaveFile._bytes_to_hex(
                b"\xBB" * (SaveFile.PARTS_BLOCK_SIZE - 1)
            )
            _write_raw_snapshot_json(path, payload)

            with self.assertRaises(ValueError) as caught:
                SaveFile.load_snapshot_library_entry(path, library_root=Path(tmp_dir_text))

        self.assertIn(
            f"has invalid normalized sidecar block size {SaveFile.PARTS_BLOCK_SIZE - 1}",
            str(caught.exception),
        )

    def test_load_snapshot_library_entry_rejects_invalid_sidecar_signature_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            path = Path(tmp_dir_text) / "car_build_snapshot_Bad_Sidecar_Signature.json"
            payload = _snapshot_json_payload(display_name="Bad Sidecar Signature", sidecar_block=_normalized_block(0x52))
            payload["optional_visual_sidecar"]["owned_record_signature_clone_hex"] = SaveFile._bytes_to_hex(
                b"\xCC" * 7
            )
            _write_raw_snapshot_json(path, payload)

            with self.assertRaises(ValueError) as caught:
                SaveFile.load_snapshot_library_entry(path, library_root=Path(tmp_dir_text))

        self.assertIn("has invalid sidecar signature length 7", str(caught.exception))

    def test_load_snapshot_library_entry_rejects_invalid_sidecar_marker_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            path = Path(tmp_dir_text) / "car_build_snapshot_Bad_Sidecar_Marker.json"
            payload = _snapshot_json_payload(display_name="Bad Sidecar Marker", sidecar_block=_normalized_block(0x53))
            payload["optional_visual_sidecar"]["sidecar_marker_hex"] = SaveFile._bytes_to_hex(b"\xFF\xCD\xCD")
            _write_raw_snapshot_json(path, payload)

            with self.assertRaises(ValueError) as caught:
                SaveFile.load_snapshot_library_entry(path, library_root=Path(tmp_dir_text))

        self.assertIn("has invalid sidecar marker length 3", str(caught.exception))


class SnapshotLibraryRoundTripTests(unittest.TestCase):
    def _round_trip_snapshot_dict(self, snapshot: FullCarBuildSnapshot) -> tuple[dict, SnapshotLibraryEntry]:
        sf = object.__new__(SaveFile)
        sf.path = Path("round-trip-source-save")
        payload = sf.snapshot_to_dict(snapshot)
        with tempfile.TemporaryDirectory() as tmp_dir_text:
            root = Path(tmp_dir_text)
            path = root / f"{SaveFile.SNAPSHOT_FILE_PREFIX}Round_Trip.json"
            _write_raw_snapshot_json(path, payload)
            entry = SaveFile.load_snapshot_library_entry(path, library_root=root)
        return payload, entry

    def test_snapshot_to_dict_round_trip_preserves_primary_fields_without_sidecar(self) -> None:
        snapshot = _make_full_car_build_snapshot(with_sidecar=False)

        payload, entry = self._round_trip_snapshot_dict(snapshot)

        self.assertEqual(payload["kind"], SaveFile.SNAPSHOT_KIND)
        self.assertEqual(entry.display_name, snapshot.display_name)
        self.assertEqual(entry.source_kind, snapshot.source_kind)
        self.assertEqual(entry.primary_owned_record_template.car_number, snapshot.primary_owned_record_template.car_number)
        self.assertEqual(entry.primary_owned_record_template.signature, snapshot.primary_owned_record_template.signature)
        self.assertEqual(entry.primary_owned_record_template.location_bits, snapshot.primary_owned_record_template.location_bits)
        self.assertEqual(entry.primary_owned_record_template.misc_bits, snapshot.primary_owned_record_template.misc_bits)
        self.assertEqual(entry.normalized_primary_build_block, snapshot.normalized_primary_build_block)
        self.assertEqual(entry.performance_levels, snapshot.performance_levels)
        self.assertFalse(entry.has_visual_sidecar)
        self.assertIsNone(entry.optional_visual_sidecar)

    def test_snapshot_to_dict_round_trip_preserves_primary_and_sidecar_fields(self) -> None:
        snapshot = _make_full_car_build_snapshot(with_sidecar=True)

        payload, entry = self._round_trip_snapshot_dict(snapshot)

        self.assertEqual(payload["kind"], SaveFile.SNAPSHOT_KIND)
        self.assertEqual(entry.display_name, snapshot.display_name)
        self.assertEqual(entry.source_kind, snapshot.source_kind)
        self.assertEqual(entry.primary_owned_record_template.car_number, snapshot.primary_owned_record_template.car_number)
        self.assertEqual(entry.primary_owned_record_template.signature, snapshot.primary_owned_record_template.signature)
        self.assertEqual(entry.primary_owned_record_template.location_bits, snapshot.primary_owned_record_template.location_bits)
        self.assertEqual(entry.primary_owned_record_template.misc_bits, snapshot.primary_owned_record_template.misc_bits)
        self.assertEqual(entry.normalized_primary_build_block, snapshot.normalized_primary_build_block)
        self.assertEqual(entry.performance_levels, snapshot.performance_levels)
        self.assertTrue(entry.has_visual_sidecar)
        self.assertIsNotNone(entry.optional_visual_sidecar)
        self.assertIsNotNone(snapshot.optional_visual_sidecar)
        self.assertEqual(
            entry.optional_visual_sidecar.owned_record_signature_clone,
            snapshot.optional_visual_sidecar.owned_record_signature_clone,
        )
        self.assertEqual(
            entry.optional_visual_sidecar.owned_record_location_bits,
            snapshot.optional_visual_sidecar.owned_record_location_bits,
        )
        self.assertEqual(
            entry.optional_visual_sidecar.owned_record_misc_bits,
            snapshot.optional_visual_sidecar.owned_record_misc_bits,
        )
        self.assertEqual(
            entry.optional_visual_sidecar.sidecar_parts_slot_offset,
            snapshot.optional_visual_sidecar.sidecar_parts_slot_offset,
        )
        self.assertEqual(
            entry.optional_visual_sidecar.normalized_sidecar_build_block,
            snapshot.optional_visual_sidecar.normalized_sidecar_build_block,
        )
        self.assertEqual(
            entry.optional_visual_sidecar.sidecar_marker,
            snapshot.optional_visual_sidecar.sidecar_build_block[
                SaveFile.PARTS_MARKER_OFFSET:SaveFile.PARTS_MARKER_OFFSET + 4
            ],
        )


class SnapshotInjectionPlannerTests(unittest.TestCase):
    def test_my_cars_plan_uses_first_reusable_owned_and_parts_slots(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot(requires_unresolved_global_visual_state=True)

        sf.get_owned_car_slot_statuses = lambda **kwargs: [
            _owned_slot(0, reusable=False),
            _owned_slot(1, reusable=True),
        ]
        sf.get_parts_slot_statuses = lambda **kwargs: [
            _parts_slot(31, reusable=False),
            _parts_slot(32, reusable=True),
        ]

        plan = sf.plan_snapshot_injection(snapshot, "my_cars")

        self.assertIsNone(plan.refusal_reason)
        self.assertEqual(plan.target_mode, "my_cars")
        self.assertEqual(plan.target_location_bits, SaveFile.MY_CARS_FLAG)
        self.assertEqual(plan.target_owned_abs_off, SaveFile.CAREER_VEHICLE_BASE_OFFSET + SaveFile.CAREER_VEHICLE_SIZE)
        self.assertEqual(plan.target_parts_slot, 32)
        self.assertIsNone(plan.target_career_slot)
        self.assertEqual(plan.warnings, ("Global visual table 0x5577 is not injected in v1.",))

    def test_sidecar_plan_requires_adjacent_owned_and_parts_slots(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot(sidecar_offset=1)
        primary_owned_abs = SaveFile.CAREER_VEHICLE_BASE_OFFSET + 0x40

        sf.get_owned_car_slot_statuses = lambda **kwargs: [
            _owned_slot(3, reusable=True, abs_off=primary_owned_abs),
            _owned_slot(4, reusable=True, abs_off=primary_owned_abs + SaveFile.CAREER_VEHICLE_SIZE),
        ]
        sf.get_parts_slot_statuses = lambda **kwargs: [
            _parts_slot(31, reusable=True),
            _parts_slot(32, reusable=True),
        ]

        plan = sf.plan_snapshot_injection(snapshot, "my_cars")

        self.assertIsNone(plan.refusal_reason)
        self.assertEqual(plan.target_owned_abs_off, primary_owned_abs)
        self.assertEqual(plan.target_sidecar_owned_abs_off, primary_owned_abs + SaveFile.CAREER_VEHICLE_SIZE)
        self.assertEqual(plan.target_parts_slot, 31)
        self.assertEqual(plan.target_sidecar_parts_slot, 32)

    def test_sidecar_plan_refuses_non_adjacent_parts_slots(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot(sidecar_offset=1)
        primary_owned_abs = SaveFile.CAREER_VEHICLE_BASE_OFFSET + 0x80

        sf.get_owned_car_slot_statuses = lambda **kwargs: [
            _owned_slot(5, reusable=True, abs_off=primary_owned_abs),
            _owned_slot(6, reusable=True, abs_off=primary_owned_abs + SaveFile.CAREER_VEHICLE_SIZE),
        ]
        sf.get_parts_slot_statuses = lambda **kwargs: [
            _parts_slot(31, reusable=True),
            _parts_slot(33, reusable=True),
        ]

        plan = sf.plan_snapshot_injection(snapshot, "my_cars")

        self.assertEqual(plan.refusal_reason, "No adjacent empty parts slot for sidecar")
        self.assertEqual(plan.target_owned_abs_off, primary_owned_abs)
        self.assertIsNone(plan.target_parts_slot)
        self.assertIsNone(plan.target_sidecar_parts_slot)

    def test_sidecar_plan_refuses_unsupported_sidecar_offset_before_allocating(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot(sidecar_offset=2)
        sf.get_owned_car_slot_statuses = lambda **kwargs: self.fail("owned slots should not be queried")
        sf.get_parts_slot_statuses = lambda **kwargs: self.fail("parts slots should not be queried")

        plan = sf.plan_snapshot_injection(snapshot, "my_cars")

        self.assertEqual(plan.refusal_reason, "Only +1 sidecar snapshots are supported")
        self.assertIsNone(plan.target_owned_abs_off)
        self.assertIsNone(plan.target_parts_slot)

    def test_plan_refuses_unsupported_target_and_keeps_template_location_bits(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot(location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)

        plan = sf.plan_snapshot_injection(snapshot, "boot")

        self.assertEqual(plan.refusal_reason, "Unsupported injector target: boot")
        self.assertEqual(plan.target_location_bits, SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)
        self.assertIsNone(plan.target_owned_abs_off)
        self.assertIsNone(plan.target_parts_slot)

    def test_plan_refuses_sidecar_snapshot_with_missing_sidecar_payload(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = replace(_make_snapshot(sidecar_offset=1), optional_visual_sidecar=None)
        sf.get_owned_car_slot_statuses = lambda **kwargs: self.fail("owned slots should not be queried")
        sf.get_parts_slot_statuses = lambda **kwargs: self.fail("parts slots should not be queried")

        plan = sf.plan_snapshot_injection(snapshot, "my_cars")

        self.assertEqual(plan.refusal_reason, "Snapshot sidecar payload is missing")
        self.assertIsNone(plan.target_owned_abs_off)
        self.assertIsNone(plan.target_parts_slot)

    def test_plan_refuses_when_no_reusable_owned_slots_exist(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot()
        sf.get_owned_car_slot_statuses = lambda **kwargs: [_owned_slot(0, reusable=False)]
        sf.get_parts_slot_statuses = lambda **kwargs: self.fail("parts slots should not be queried")

        plan = sf.plan_snapshot_injection(snapshot, "my_cars")

        self.assertEqual(plan.refusal_reason, "No validated empty owned-car slots available")
        self.assertIsNone(plan.target_owned_abs_off)
        self.assertIsNone(plan.target_parts_slot)

    def test_plan_refuses_sidecar_when_reusable_owned_slots_are_not_adjacent(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot(sidecar_offset=1)
        first_abs = SaveFile.CAREER_VEHICLE_BASE_OFFSET + 0x100
        sf.get_owned_car_slot_statuses = lambda **kwargs: [
            _owned_slot(8, reusable=True, abs_off=first_abs),
            _owned_slot(9, reusable=True, abs_off=first_abs + SaveFile.CAREER_VEHICLE_SIZE * 2),
        ]
        sf.get_parts_slot_statuses = lambda **kwargs: self.fail("parts slots should not be queried")

        plan = sf.plan_snapshot_injection(snapshot, "my_cars")

        self.assertEqual(plan.refusal_reason, "No adjacent empty owned-car slot for sidecar")
        self.assertIsNone(plan.target_owned_abs_off)
        self.assertIsNone(plan.target_sidecar_owned_abs_off)
        self.assertIsNone(plan.target_parts_slot)

    def test_plan_refuses_desired_career_slot_when_not_reusable(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot()
        owned_abs = SaveFile.CAREER_VEHICLE_BASE_OFFSET + 0x140
        sf.get_owned_car_slot_statuses = lambda **kwargs: [_owned_slot(10, reusable=True, abs_off=owned_abs)]
        sf.get_parts_slot_statuses = lambda **kwargs: [_parts_slot(31, reusable=True)]
        sf.get_career_slot_statuses = lambda **kwargs: [_career_slot(3, reusable=False)]

        plan = sf.plan_snapshot_injection(snapshot, "career", desired_career_slot=3)

        self.assertEqual(plan.refusal_reason, "Career slot 4 is not a validated empty slot")
        self.assertEqual(plan.target_owned_abs_off, owned_abs)
        self.assertEqual(plan.target_parts_slot, 31)
        self.assertIsNone(plan.target_career_slot)

    def test_plan_refuses_career_target_when_no_reusable_career_slots_exist(self) -> None:
        sf = object.__new__(SaveFile)
        snapshot = _make_snapshot()
        sf.get_owned_car_slot_statuses = lambda **kwargs: [_owned_slot(11, reusable=True)]
        sf.get_parts_slot_statuses = lambda **kwargs: [_parts_slot(31, reusable=True)]
        sf.get_career_slot_statuses = lambda **kwargs: [_career_slot(0, reusable=False)]

        plan = sf.plan_snapshot_injection(snapshot, "career")

        self.assertEqual(plan.refusal_reason, "No validated empty career slots available")
        self.assertIsNone(plan.target_career_slot)


class SnapshotInjectionWriteTests(unittest.TestCase):
    def test_inject_snapshot_writes_primary_and_sidecar_records_and_parts_blocks(self) -> None:
        sf = _new_savefile_buffer()
        primary_block = _normalized_block(0x20)
        sidecar_block = _normalized_block(0x80)
        signature = b"\x44\x45\x46\x47\x48\x49\x4A\x4B"
        snapshot = _make_snapshot(
            signature=signature,
            normalized_block=primary_block,
            sidecar_offset=1,
            sidecar_block=sidecar_block,
        )
        owned_abs = SaveFile.CAREER_VEHICLE_BASE_OFFSET
        sidecar_owned_abs = owned_abs + SaveFile.CAREER_VEHICLE_SIZE

        sf.get_owned_car_records = lambda: [_existing_record(car_number=7)]
        sf.get_owned_car_slot_statuses = lambda **kwargs: [
            _owned_slot(0, reusable=True, abs_off=owned_abs),
            _owned_slot(1, reusable=True, abs_off=sidecar_owned_abs),
        ]
        sf.get_parts_slot_statuses = lambda **kwargs: [
            _parts_slot(31, reusable=True),
            _parts_slot(32, reusable=True),
        ]

        plan = sf.inject_snapshot(snapshot, "my_cars")

        self.assertIsNone(plan.refusal_reason)
        self.assertEqual(
            bytes(sf.data[_parts_abs_off(31):_parts_abs_off(31) + SaveFile.PARTS_BLOCK_SIZE]),
            _block_with_marker(primary_block, b"\x1F\xCD\xCD\xCD"),
        )
        self.assertEqual(
            bytes(sf.data[_parts_abs_off(32):_parts_abs_off(32) + SaveFile.PARTS_BLOCK_SIZE]),
            _block_with_marker(sidecar_block, SaveFile.EMPTY_PARTS_BLOCK_MARKER),
        )

        primary_record = _read_owned_record(bytes(sf.data[owned_abs:owned_abs + SaveFile.CAREER_VEHICLE_SIZE]))
        sidecar_record = _read_owned_record(bytes(sf.data[sidecar_owned_abs:sidecar_owned_abs + SaveFile.CAREER_VEHICLE_SIZE]))

        self.assertEqual(primary_record["car_number"], 8)
        self.assertEqual(primary_record["signature"], signature)
        self.assertEqual(primary_record["location_bits"], SaveFile.MY_CARS_FLAG)
        self.assertEqual(primary_record["misc_bits"], 9)
        self.assertEqual(primary_record["parts_slot"], 31)
        self.assertEqual(primary_record["career_slot"], SaveFile.EMPTY_CAREER_SLOT)
        self.assertEqual(primary_record["sentinel"], SaveFile.CAREER_VEHICLE_SENTINEL)

        self.assertEqual(sidecar_record["car_number"], SaveFile.EMPTY_CAR_NUMBER)
        self.assertEqual(sidecar_record["signature"], signature)
        self.assertEqual(sidecar_record["location_bits"], SaveFile.MY_CARS_FLAG)
        self.assertEqual(sidecar_record["misc_bits"], 12)
        self.assertEqual(sidecar_record["parts_slot"], 32)
        self.assertEqual(sidecar_record["career_slot"], SaveFile.EMPTY_CAREER_SLOT)
        self.assertEqual(sidecar_record["sentinel"], SaveFile.CAREER_VEHICLE_SENTINEL)

    def test_career_injection_preserves_pink_slip_bits_and_canonicalizes_pursuit_slot(self) -> None:
        sf = _new_savefile_buffer()
        signature = b"\x51\x52\x53\x54\x55\x56\x57\x58"
        snapshot = _make_snapshot(
            source_kind="Pink Slip",
            location_bits=SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG,
            signature=signature,
        )
        owned_abs = SaveFile.CAREER_VEHICLE_BASE_OFFSET
        pursuit_abs = SaveFile.GARAGE_BASE_OFFSET
        dirty_pursuit = bytearray(SaveFile.GARAGE_SLOT_SIZE)
        dirty_pursuit[0] = SaveFile.GARAGE_EMPTY_HANDLE
        dirty_pursuit[1] = 0xCD
        dirty_pursuit[SaveFile.GARAGE_IMPOUND_MAX_BUSTED_OFFSET] = SaveFile.GARAGE_MAX_BUSTED_BASE
        dirty_pursuit[0x0A:0x0C] = b"\xCD\xCD"
        SaveFile._write_pursuit_heat_into(dirty_pursuit, 4.0)
        dirty_pursuit[SaveFile.GARAGE_IMPOUND_STATE_OFFSET] = 2
        dirty_pursuit[SaveFile.GARAGE_IMPOUND_DAYS_BEFORE_RELEASE_OFFSET] = 5
        struct.pack_into("<H", dirty_pursuit, SaveFile.GARAGE_IMPOUND_EVADE_COUNT_OFFSET, 3)
        struct.pack_into("<H", dirty_pursuit, SaveFile.GARAGE_UNSERVED_INFRACTIONS_OFFSET, 11)
        struct.pack_into("<H", dirty_pursuit, SaveFile.GARAGE_SERVED_INFRACTIONS_OFFSET, 13)
        struct.pack_into("<I", dirty_pursuit, SaveFile.GARAGE_BOUNTY_OFFSET, 123456)
        struct.pack_into("<H", dirty_pursuit, SaveFile.GARAGE_ESCAPED_OFFSET, 7)
        struct.pack_into("<H", dirty_pursuit, SaveFile.GARAGE_BUSTED_OFFSET, 8)
        sf.data[pursuit_abs:pursuit_abs + SaveFile.GARAGE_SLOT_SIZE] = dirty_pursuit

        sf.get_owned_car_records = lambda: [_existing_record(car_number=41)]
        sf.get_owned_car_slot_statuses = lambda **kwargs: [_owned_slot(0, reusable=True, abs_off=owned_abs)]
        sf.get_parts_slot_statuses = lambda **kwargs: [_parts_slot(31, reusable=True)]
        sf.get_career_slot_statuses = lambda **kwargs: [_career_slot(0, reusable=True)]
        sf.count_career_like_owned_records = lambda **kwargs: 0
        sf.get_active_career_record = lambda: object()

        plan = sf.inject_snapshot(snapshot, "career", desired_career_slot=0)

        self.assertIsNone(plan.refusal_reason)
        self.assertEqual(plan.target_career_slot, 0)
        record = _read_owned_record(bytes(sf.data[owned_abs:owned_abs + SaveFile.CAREER_VEHICLE_SIZE]))
        self.assertEqual(record["car_number"], 42)
        self.assertEqual(record["signature"], signature)
        self.assertEqual(record["location_bits"], SaveFile.CAREER_FLAG | SaveFile.PINK_SLIP_FLAG)
        self.assertEqual(record["parts_slot"], 31)
        self.assertEqual(record["career_slot"], 0)

        repaired = bytes(sf.data[pursuit_abs:pursuit_abs + SaveFile.GARAGE_SLOT_SIZE])
        repaired_heat = struct.unpack_from("<f", repaired, SaveFile.GARAGE_HEAT_FLOAT_OFFSET)[0]
        self.assertEqual(repaired[0], 0)
        self.assertEqual(repaired[1], 0xCD)
        self.assertEqual(repaired[SaveFile.GARAGE_IMPOUND_MAX_BUSTED_OFFSET], SaveFile.GARAGE_MAX_BUSTED_BASE)
        self.assertEqual(repaired[0x0A:0x0C], b"\xCD\xCD")
        self.assertAlmostEqual(repaired_heat, SaveFile.GARAGE_HEAT_NATIVE_FRESH)
        self.assertEqual(repaired[SaveFile.GARAGE_IMPOUND_TIMES_BUSTED_OFFSET], 0)
        self.assertEqual(repaired[SaveFile.GARAGE_IMPOUND_STATE_OFFSET], 0)
        self.assertEqual(repaired[SaveFile.GARAGE_IMPOUND_DAYS_BEFORE_RELEASE_OFFSET], 0)
        self.assertEqual(struct.unpack_from("<H", repaired, SaveFile.GARAGE_IMPOUND_EVADE_COUNT_OFFSET)[0], 0)
        for block_off in (SaveFile.GARAGE_UNSERVED_INFRACTIONS_OFFSET, SaveFile.GARAGE_SERVED_INFRACTIONS_OFFSET):
            for counter in range(SaveFile.GARAGE_INFRACTION_COUNTER_COUNT):
                self.assertEqual(struct.unpack_from("<H", repaired, block_off + counter * 2)[0], 0)
        self.assertEqual(struct.unpack_from("<I", repaired, SaveFile.GARAGE_BOUNTY_OFFSET)[0], 0)
        self.assertEqual(struct.unpack_from("<H", repaired, SaveFile.GARAGE_ESCAPED_OFFSET)[0], 0)
        self.assertEqual(struct.unpack_from("<H", repaired, SaveFile.GARAGE_BUSTED_OFFSET)[0], 0)

    def test_inject_snapshot_refusal_raises_value_error_without_modifying_buffer(self) -> None:
        sf = _new_savefile_buffer()
        original = bytes(sf.data)
        snapshot = _make_snapshot()
        sf.get_owned_car_slot_statuses = lambda **kwargs: []
        sf.get_parts_slot_statuses = lambda **kwargs: self.fail("parts slots should not be queried")

        with self.assertRaises(ValueError) as caught:
            sf.inject_snapshot(snapshot, "my_cars")

        self.assertEqual(str(caught.exception), "No validated empty owned-car slots available")
        self.assertEqual(bytes(sf.data), original)


if __name__ == "__main__":
    unittest.main()
