"""Xbox 360 / nfsmw-nx wire-format adapter for the original PC editor.

The original editing engine works on its canonical PC representation. Only
named, typed regions are translated back to the native file. Unknown native
bytes, the console-only prelude and the platform-specific tail survive intact.
The public ``data`` buffer always contains the native file, so the unchanged
GUI's disk comparisons, reload and staged-save workflow remain meaningful.

Schema evidence: the supplied PC sources, the supplied 62688-byte native save,
and the GManager, GActivity, TableVar, FECustomizationRecord and FECarRecord
definitions in dbalatoni13/nfsmw (commit 1f2cdd7996791c81a580b3f7b36b44d4f9f6719c).
"""
from __future__ import annotations

import hashlib
import struct
from functools import lru_cache, wraps
from pathlib import Path

from core.checksums import ea_crc32
from core.models import IntegrityStatus
from core.savefile import SaveFile

PC_SIZE = 0xF86C
SWITCH_SIZE = 0xF4E0
GAME_START = 0x34
GAME_END = 0x4034


def is_switch_save(data: bytes | bytearray) -> bool:
    return (len(data) == SWITCH_SIZE and data[:4] == b"MC02"
            and int.from_bytes(data[4:8], "big") == SWITCH_SIZE)


def _require_span(buf: bytes | bytearray, start: int, size: int, label: str) -> None:
    if start < 0 or size < 0 or start > len(buf) or size > len(buf) - start:
        raise ValueError(f"{label} span out of bounds: offset {start}, size {size}, buffer {len(buf)}")


def _reverse(buf: bytearray, start: int, size: int) -> None:
    _require_span(buf, start, size, "Typed field")
    buf[start:start + size] = buf[start:start + size][::-1]


def _words(raw: bytes, width: int) -> bytes:
    if len(raw) % width:
        raise ValueError("Misaligned typed save region")
    return b"".join(raw[i:i + width][::-1] for i in range(0, len(raw), width))


def _lua_table(buf: bytearray, start: int, size: int, to_pc: bool) -> None:
    """Translate TableVar bitfields; packed identifiers remain byte strings."""
    _require_span(buf, start, size, "Persistent Lua table")
    end = start + size

    def fields(pos):
        raw = buf[pos]
        if to_pc:
            kind = raw >> 4
            boolean, packed, key, valid = ((raw >> bit) & 1 for bit in (3, 2, 1, 0))
        else:
            kind = raw & 15
            boolean, packed, key, valid = ((raw >> bit) & 1 for bit in (4, 5, 6, 7))
        return kind, boolean, packed, key, valid

    @lru_cache(None)
    def walk(pos, expect_key):
        if pos >= end:
            return ()
        kind, boolean, packed, key, valid = fields(pos)
        if not valid:
            return ((),) if buf[pos] == 0 and pos + 1 == end and expect_key else ()
        if bool(key) != expect_key or kind not in (1, 3, 4):
            return ()
        if kind == 4:
            # PackIdentifier streams may contain zero bytes internally. A
            # boundary must also produce one unique valid key/value stream.
            candidates = [i + 1 for i in range(pos + 1, end) if buf[i] == 0]
            if not packed:
                candidates = candidates[:1]
        else:
            candidates = [pos + 1 + ((1 if packed else 4) if kind == 3 else 0)]
        answers = []
        for after in candidates:
            for tail in walk(after, not expect_key):
                answer = ((pos, kind, packed),) + tail
                # A packed identifier must not swallow subsequent complete
                # key/value entries. Prefer the complete entry segmentation;
                # equally complete competing segmentations are refused.
                if answers and len(answer) < len(answers[0]):
                    continue
                if answers and len(answer) > len(answers[0]):
                    answers.clear()
                if len(answers) < 2:
                    answers.append(answer)
        return tuple(answers)

    paths = walk(start, True)
    if len(paths) != 1:
        raise ValueError(f"Persistent Lua table at 0x{start + GAME_START:X} has {len(paths)} valid parses ({size} bytes)")
    for pos, kind, packed in paths[0]:
        kind, boolean, packed, key, valid = fields(pos)
        buf[pos] = (kind | boolean << 4 | packed << 5 | key << 6 | valid << 7) if to_pc else (kind << 4 | boolean << 3 | packed << 2 | key << 1 | valid)
        if kind == 3 and not packed:
            _reverse(buf, pos + 1, 4)


def game_region(raw: bytes, to_pc: bool) -> bytes:
    """Convert the self-checksummed 16 KiB gameplay section field by field."""
    if len(raw) != GAME_END - GAME_START:
        raise ValueError("Invalid gameplay-section size")
    buf = bytearray(raw)
    order = ">" if to_pc else "<"
    expected = b"emaG" if to_pc else b"Game"
    if buf[16:20] != expected:
        raise ValueError("Unsupported gameplay-section magic")
    header = struct.unpack_from(order + "11I", buf, 16)
    _, version, persistent, timers, types, milestones, traps, gates, hiding_bits, bin_bytes, sms = header
    if version != 8 or persistent > 256 or timers > 64 or types > 128 or milestones > 256 or traps > 128:
        raise ValueError("Unsupported gameplay serialization version/counts")
    for pos in range(16, 60, 4):
        _reverse(buf, pos, 4)
    pos = 0x80  # persistent pool begins at absolute 0xB4
    _require_span(buf, pos, persistent * 16, "Persistent activity headers")
    for _ in range(persistent):
        _require_span(buf, pos, 16, "Persistent activity header")
        _key, size = struct.unpack_from(order + "II", buf, pos)
        if size < 8:
            raise ValueError("Invalid persistent activity size")
        record_size = (8 + size + 15) & ~15
        _require_span(buf, pos, record_size, "Aligned persistent activity")
        table_size = struct.unpack_from(order + "H", buf, pos + 14)[0]
        if table_size != size - 8:
            raise ValueError("Unsupported persistent activity payload")
        for rel, width in ((0, 4), (4, 4), (8, 4), (12, 2), (14, 2)):
            _reverse(buf, pos + rel, width)
        if table_size:
            _lua_table(buf, pos + 16, table_size, to_pc)
        pos += record_size
    # Each array is aligned relative to the start of the gameplay section.
    align = lambda value: (value + 7) & ~7
    _require_span(buf, pos, timers * 32, "Saved timers")
    for _ in range(timers):
        _reverse(buf, pos, 4)  # interval
        _reverse(buf, pos + 8, 4)  # elapsed; running and name are bytes
        pos += 32
    pos = align(pos)
    _require_span(buf, pos, types * 16, "Milestone types")
    for _ in range(types):
        for rel in range(0, 16, 4):
            _reverse(buf, pos + rel, 4)
        pos += 16
    pos = align(pos)
    _require_span(buf, pos, milestones * 20, "Milestone records")
    for _ in range(milestones):
        for rel, width in ((0, 4), (4, 4), (10, 2), (12, 4), (16, 4)):
            _reverse(buf, pos + rel, width)
        pos += 20
    pos = align(pos)
    _require_span(buf, pos, traps * 20, "Speed-trap records")
    for _ in range(traps):
        # GSpeedTrap: flags H, bin H, key I, camera I, required f, recorded f.
        for rel, width in ((0, 2), (2, 2), (4, 4), (8, 4), (12, 4), (16, 4)):
            _reverse(buf, pos + rel, width)
        pos += 20
    pos = align(pos)
    _require_span(buf, pos, gates * 4, "Unlocked gates")
    for _ in range(gates):
        _reverse(buf, pos, 4)
        pos += 4
    pos = align(pos)
    hiding_bytes = (hiding_bits + 7) // 8
    if hiding_bytes % 4:
        raise ValueError("Unsupported hiding-spot bitset")
    _require_span(buf, pos, hiding_bytes, "Hiding-spot bitset")
    for rel in range(0, hiding_bytes, 4):
        _reverse(buf, pos + rel, 4)
    pos = align(pos + hiding_bytes)
    if bin_bytes < 4:
        raise ValueError("Invalid race-bin statistics")
    _require_span(buf, pos, bin_bytes, "Race-bin statistics")
    count = struct.unpack_from(order + "I", buf, pos)[0]
    if bin_bytes != 4 + count * 8:
        raise ValueError("Unsupported race-bin statistics layout")
    _reverse(buf, pos, 4)
    for rel in range(4, bin_bytes, 2):
        _reverse(buf, pos + rel, 2)
    pos = align(pos + bin_bytes)
    _require_span(buf, pos, sms * 4, "Pending SMS")
    for _ in range(sms):
        _reverse(buf, pos, 4)
        pos += 4
    pos = align(pos)
    _require_span(buf, pos, 32, "Gameplay footer")
    # Saved free-roam marker keys. The surrounding byte/padding fields stay put.
    for rel in (8, 24):
        _reverse(buf, pos + rel, 4)
    buf[:16] = hashlib.md5(buf[16:]).digest()
    return bytes(buf)


def _settings(raw: bytes) -> bytes:
    buf = bytearray(raw)
    _reverse(buf, 0, 2)  # AdaptiveDifficulty at 0x403D
    _reverse(buf, 2, 4)  # SpecialFlags is a FULL u32 at 0x403F
    for pos in range(6, 606, 4):
        _reverse(buf, pos + 2, 2)  # SMS id/flags are bytes; sort order is u16
    _reverse(buf, 606, 2)
    return bytes(buf)


def _race_belt(raw: bytes) -> bytes:
    buf = bytearray(raw)
    _reverse(buf, 0, 4)  # trailing score of the preceding static race
    _reverse(buf, 4, 2)
    _reverse(buf, 6, 2)
    for pos in range(8, 8 + 248 * 16, 16):
        for rel, width in ((0, 4), (4, 4), (8, 4), (12, 2), (14, 2)):
            _reverse(buf, pos + rel, width)
    # The following unlock data consists of byte fields (UnlockDatum).
    for rel, width in ((0, 4), (4, 4), (8, 4), (12, 2), (14, 2)):
        _reverse(buf, 8 + 248 * 16 + rel, width)
    return bytes(buf)


def _owned(raw: bytes, to_pc: bool) -> bytes:
    buf = bytearray(raw)
    native_pad, editor_pad = b"\xAA\xAA", b"\xCD\xCD"
    source, target = (native_pad, editor_pad) if to_pc else (editor_pad, native_pad)
    for pos in range(0, len(buf), 20):
        for rel in (0, 4, 8, 12):
            _reverse(buf, pos + rel, 4)
        if buf[pos + 18:pos + 20] == source:
            buf[pos + 18:pos + 20] = target
    return bytes(buf)


def _parts(raw: bytes, to_pc: bool) -> bytes:
    buf = bytearray(raw)
    source, target = (0xAA, 0xCD) if to_pc else (0xCD, 0xAA)
    for pos in range(0, len(buf), 0x198):
        for rel in range(0, 0x116, 2):
            _reverse(buf, pos + rel, 2)
        if buf[pos + 0x116:pos + 0x118] == bytes((source, source)):
            buf[pos + 0x116:pos + 0x118] = bytes((target, target))
        for rel in range(0x118, 0x194, 4):
            _reverse(buf, pos + rel, 4)
        if buf[pos + 0x195:pos + 0x198] == bytes((source,)) * 3:
            buf[pos + 0x195:pos + 0x198] = bytes((target,)) * 3
    return bytes(buf)


def _pursuits(raw: bytes, to_pc: bool) -> bytes:
    buf = bytearray(raw)
    source, target = (0xAA, 0xCD) if to_pc else (0xCD, 0xAA)
    for pos in range(0, len(buf), 0x38):
        for rel in (1, 10, 11):
            if buf[pos + rel] == source:
                buf[pos + rel] = target
        for rel in (12, 16):
            _reverse(buf, pos + rel, 4)
        for rel in range(20, 56, 2):
            _reverse(buf, pos + rel, 2)
    return bytes(buf)


def _history(raw: bytes) -> bytes:
    return raw[:4][::-1] + _words(raw[4:], 2)


class SwitchCodec:
    """Reversible translation of the editor's complete writable surface."""
    # PC offset, native offset, length, converter name.
    REGIONS = (
        (0x34, 0x34, 0x4000, "game"),
        (0x4034, 0x4034, 4, "u32"),
        (0x4038, 0x4038, 1, "bytes"),
        (0x4039, 0x4039, 4, "u32"),
        (0x403D, 0x403D, 608, "settings"),
        (0x42B9, 0x42B9, 0x5739 - 0x42B9, "races"),
        (0x5739, 0x5739, 63 * 12, "u32"),
        (0x5A31, 0x5A31, 0x24, "bytes"),
        (0x6219, 0x6221, 119 * 20, "owned"),
        (0x9CCD, 0x9CD5, 44 * 0x198, "parts"),
        (0xE2ED, 0xE2F5, 25 * 0x38, "pursuits"),
        (0xE865, 0xE86D, 40, "history"),
    )

    def __init__(self, native: bytes | bytearray):
        self.native = bytes(native)
        if not is_switch_save(native):
            raise ValueError("Expected a raw 62688-byte nfsmw-nx / Xbox 360 MC02 save")
        if struct.unpack_from(">II", native, 8) != (8, SWITCH_SIZE - 0x24):
            raise ValueError("Unsupported Xbox 360 MC02 block layout")
        if struct.unpack_from(">II", native, 0x1C) != (0x10D, SWITCH_SIZE - 0x24):
            raise ValueError("Unsupported Xbox 360 MC02 serialization version")
        self.baseline = self.decode()

    @staticmethod
    def _convert(raw: bytes, kind: str, to_pc: bool) -> bytes:
        if kind == "game": return game_region(raw, to_pc)
        if kind == "u32": return _words(raw, 4)
        if kind == "settings": return _settings(raw)
        if kind == "races": return _race_belt(raw)
        if kind == "owned": return _owned(raw, to_pc)
        if kind == "parts": return _parts(raw, to_pc)
        if kind == "pursuits": return _pursuits(raw, to_pc)
        if kind == "history": return _history(raw)
        return raw

    def decode(self) -> bytearray:
        buf = bytearray(PC_SIZE)
        buf[:len(self.native) - 16] = self.native[:-16]
        for pc, native, size, kind in self.REGIONS:
            buf[pc:pc + size] = self._convert(self.native[native:native + size], kind, True)
        # These two legacy PC transplant spans are undocumented PC settings,
        # not transferable console progression. Keep their native bytes intact.
        buf[0x5B41] = 0
        buf[0x5B62:0x5B64] = bytes(2)
        for pos in range(4, 0x24, 4):
            _reverse(buf, pos, 4)
        struct.pack_into("<I", buf, 4, PC_SIZE)
        _repair(buf, "<")
        return buf

    def encode(self, working: bytes | bytearray) -> bytearray:
        if len(working) != PC_SIZE:
            raise ValueError("Editor changed the canonical buffer size")
        buf = bytearray(self.native)
        for pc, native, size, kind in self.REGIONS:
            # Padding normalization is lossy (both native AA and CD can
            # decode to CD). Never re-encode an unedited neighbour record.
            stride = {"owned": 20, "parts": 0x198, "pursuits": 0x38}.get(kind, size)
            for rel in range(0, size, stride):
                value = bytes(working[pc + rel:pc + rel + stride])
                if value != self.baseline[pc + rel:pc + rel + stride]:
                    buf[native + rel:native + rel + stride] = self._convert(value, kind, False)
        return buf


def _repair(buf: bytearray, order: str) -> None:
    struct.pack_into(order + "I", buf, 4, len(buf))
    buf[-16:] = hashlib.md5(buf[0x34:-16]).digest()
    for pos, start, end in ((0x10, 0x1C, 0x24), (0x14, 0x24, len(buf)), (0x18, 0, 0x18)):
        struct.pack_into(order + "I", buf, pos, ea_crc32(buf[start:end]))


def editor_view(data: bytes) -> bytes:
    """Normalize raw native input for unchanged standalone progress readers."""
    return bytes(SwitchCodec(data).baseline) if is_switch_save(data) else data


class SwitchSaveFile(SaveFile):
    """Same SaveFile API and original edit engine, with native persistence."""
    def __init__(self, path, data, layout=None, hash_scheme=None):
        self.path = Path(path)
        self._codec = SwitchCodec(data)
        self._pc = SaveFile(self.path, bytearray(self._codec.baseline), layout, "md5_saved_data")
        self.layout = self._pc.layout
        self._cache_key = bytes(self._pc.data)
        self._native_cache = bytearray(data)
        self._native_snapshot = bytes(data)
        self.hash_scheme = hash_scheme or self.detect_hash_scheme()
        self.platform_name = "nfsmw-nx / Xbox 360"

    def __getattribute__(self, name):
        # Keep all original editing methods and constants on the PC engine.
        # Only methods defined here and native state live on this adapter.
        own = object.__getattribute__(self, "__dict__")
        if name in SwitchSaveFile.__dict__ or name in own or name in ("__class__", "__dict__"):
            return object.__getattribute__(self, name)
        self._adopt_external_edits()
        value = getattr(object.__getattribute__(self, "_pc"), name)
        if not callable(value):
            return value

        @wraps(value)
        def synced_call(*args, **kwargs):
            # A caller may hold both a data reference and a bound method.
            # Adopt at call time, then encode setter edits immediately into
            # the SAME bytearray so held references never become stale.
            self._adopt_external_edits()
            try:
                return value(*args, **kwargs)
            finally:
                self._sync_native_cache()

        return synced_call

    def _adopt_external_edits(self):
        # Preserve the original mutable-bytearray API, including pack_into
        # writes that bypass Python's __setitem__ hook.
        if bytes(self._native_cache) != self._native_snapshot:
            if bytes(self._pc.data) != self._cache_key:
                # Direct changes to the private engine (e.g. through a
                # retained subobject) cannot be ordered against raw writes.
                raise ValueError("Conflicting native-buffer and canonical edits; synchronize through save.data before mixing direct writes")
            codec = SwitchCodec(self._native_cache)
            self._codec = codec
            self._pc.data = bytearray(codec.baseline)
            self._pc.junkman = type(self._pc.junkman)(self._pc)
            self._cache_key = bytes(self._pc.data)
            self._native_snapshot = bytes(self._native_cache)

    def _sync_native_cache(self):
        key = bytes(self._pc.data)
        if key != self._cache_key:
            native = self._codec.encode(key)
            self._native_cache[:] = native
            self._native_snapshot = bytes(native)
            self._cache_key = key

    @property
    def data(self):
        self._adopt_external_edits()
        self._sync_native_cache()
        return self._native_cache

    @data.setter
    def data(self, value):
        # Validate before replacing the public buffer and keep held
        # references alive. Full-buffer assignment intentionally replaces
        # the current working save, just like the PC engine's data setter.
        codec = SwitchCodec(value)
        self._codec = codec
        self._pc.data = bytearray(codec.baseline)
        self._pc.junkman = type(self._pc.junkman)(self._pc)
        self._cache_key = bytes(self._pc.data)
        self._native_cache[:] = value
        self._native_snapshot = bytes(value)

    def detect_hash_scheme(self):
        buf = self.data
        return "md5_saved_data" if hashlib.md5(buf[0x34:-16]).digest() == buf[-16:] else None

    def validate_integrity(self):
        buf = self.data
        stored = int.from_bytes(buf[4:8], "big")
        details = {}
        for name, pos, start, end in (("block1", 0x10, 0x1C, 0x24), ("data", 0x14, 0x24, len(buf)), ("block2", 0x18, 0, 0x18)):
            details[name] = (int.from_bytes(buf[pos:pos + 4], "big"), ea_crc32(buf[start:end]))
        digest = hashlib.md5(buf[0x34:-16]).digest()
        return IntegrityStatus(
            hash_scheme=self.hash_scheme, md5_ok=digest == buf[-16:],
            crc_block1_ok=details["block1"][0] == details["block1"][1],
            crc_data_ok=details["data"][0] == details["data"][1],
            crc_block2_ok=details["block2"][0] == details["block2"][1],
            file_size_ok=stored == len(buf), stored_size=stored, actual_size=len(buf),
            stored_md5=bytes(buf[-16:]), computed_md5=digest, crc_details=details)

    def fix_integrity(self, force_scheme=None):
        buf = bytearray(self.data)
        _repair(buf, ">")
        self._native_cache[:] = buf
        self._native_snapshot = bytes(buf)
        self.hash_scheme = "md5_saved_data"
        return self.validate_integrity()

    def write_backup(self):
        target = self.backup_path()
        target.write_bytes(bytes(self.data))
        return target

    def save(self, out_path=None, make_backup=True):
        if make_backup:
            original = self.path.read_bytes() if self.path.exists() else bytes(self.data)
            self.backup_path().write_bytes(original)
        self.fix_integrity()
        dest = Path(out_path) if out_path is not None else self.path
        dest.write_bytes(bytes(self.data))
        return dest
