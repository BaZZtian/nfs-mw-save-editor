"""Contract tests for the web-UI boundary (`nfs_mw_save_editor.api`).

These tests exercise the REAL process boundary: they spawn
`python -m api.server` (cwd = nfs_mw_save_editor/) as a subprocess and speak
newline-delimited JSON-RPC over its stdio — no in-process shortcuts, so a
green run certifies exactly what the Electron shell will use.

Fixture save: synthetic, full-size 0xF86C buffer written to a tmp file with
`fix_integrity()` applied. Planted state: money, ASCII alias, story rank 5
(heat cap x4 — the over-cap test needs headroom to x5), and one live
pursuit record in slot 0 (canonical pad bytes, known heat/bounty) with the
remaining 24 slots empty (handle 0xFF). No owned-car record on purpose:
the resolver reports the slot as 'Unlinked vehicle' / 'Unknown', which the
open-state test asserts verbatim. No personal saves.
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from api import PROTOCOL_VERSION
from api.service import EditorService
from core.savefile import SaveFile

MONEY_PLANTED = 123_456
BOUNTY_PLANTED = 777_000
HEAT_PLANTED = 2.0
RANK_PLANTED = 5  # heat_cap_for_blacklist_rank(5) == 4
ALIAS_PLANTED = "CONTRACT"


def _build_synthetic_save(path: Path) -> None:
    data = bytearray(0xF86C)
    sf = SaveFile(path=path, data=data)
    sf.set_money(MONEY_PLANTED)
    sf.set_profile_alias(ALIAS_PLANTED)
    data[SaveFile.PLAYER_RANK_OFFSET] = RANK_PLANTED

    record = bytearray(SaveFile.GARAGE_SLOT_SIZE)
    record[0] = 0  # live handle for slot 0
    record[1] = 0xCD  # canonical pad bytes required by the live-record gate
    record[10:12] = b"\xCD\xCD"
    struct.pack_into("<f", record, SaveFile.GARAGE_HEAT_FLOAT_OFFSET, HEAT_PLANTED)
    base = SaveFile.GARAGE_BASE_OFFSET
    data[base:base + SaveFile.GARAGE_SLOT_SIZE] = record
    for slot in range(1, SaveFile.GARAGE_SLOT_COUNT):
        data[base + slot * SaveFile.GARAGE_SLOT_SIZE] = SaveFile.GARAGE_EMPTY_HANDLE

    sf.set_slot_bounty(0, BOUNTY_PLANTED)
    sf.fix_integrity()
    path.write_bytes(bytes(sf.data))


@pytest.fixture
def synthetic_save_path(tmp_path):
    path = tmp_path / "SYNTH"
    _build_synthetic_save(path)
    return path


class RpcClient:
    """Minimal NDJSON JSON-RPC client over a subprocess's stdio."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc
        self._next_id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        request = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            request["params"] = params
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, "server closed stdout unexpectedly"
        response = json.loads(line)
        assert response["id"] == self._next_id, response
        return response

    def result(self, method: str, params: dict | None = None) -> dict:
        response = self.call(method, params)
        assert "error" not in response, response.get("error")
        return response["result"]

    def error(self, method: str, params: dict | None = None) -> dict:
        response = self.call(method, params)
        assert "error" in response, response
        return response["error"]


@pytest.fixture
def server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "api.server"],
        cwd=str(PACKAGE_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        yield RpcClient(proc)
    finally:
        if proc.poll() is None:
            try:
                proc.stdin.close()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()
                proc.wait(timeout=5)


def test_hello_handshake(server):
    """hello returns PROTOCOL_VERSION and the running sys.executable."""
    result = server.result("hello")
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["pythonExe"] == sys.executable


def test_open_save_state_matches_planted_bytes(server, synthetic_save_path):
    """openSave returns SaveState whose alias/money/garage mirror exactly
    what the fixture planted; opening modifies nothing on disk."""
    on_disk_before = synthetic_save_path.read_bytes()
    state = server.result("openSave", {"path": str(synthetic_save_path)})

    assert state["opened"] is True
    assert state["path"] == str(synthetic_save_path)
    assert state["alias"] == ALIAS_PLANTED
    assert state["money"] == MONEY_PLANTED
    assert state["rapSheet"] == {
        "totalBounty": BOUNTY_PLANTED,
        "escapes": 0,
        "busts": 0,
    }
    assert state["garage"] == [
        {
            "slotIndex": 0,
            "modelName": "Unlinked vehicle",
            "bounty": BOUNTY_PLANTED,
            "heat": HEAT_PLANTED,
            "heatLevel": 2,
            "heatCap": 4,
            "source": "Unknown",
        }
    ]
    assert state["staged"] == {
        "dirty": False,
        "appliedNotSaved": False,
        "entries": [],
    }
    assert state["integrity"]["md5Ok"] is True
    assert state["warnings"] == []
    assert synthetic_save_path.read_bytes() == on_disk_before


def test_staged_money_reset_roundtrip(server, synthetic_save_path):
    """setMoney stages (dirty=true, entry have->want); resetStaged returns
    a clean state; the save buffer bytes never changed."""
    server.result("openSave", {"path": str(synthetic_save_path)})

    staged = server.result("setMoney", {"value": 555})["staged"]
    assert staged["dirty"] is True
    assert staged["appliedNotSaved"] is False  # buffer still equals disk
    assert staged["entries"] == [
        {"field": "money", "slotIndex": None, "have": MONEY_PLANTED, "want": 555}
    ]

    state = server.result("resetStaged")
    assert state["staged"] == {
        "dirty": False,
        "appliedNotSaved": False,
        "entries": [],
    }
    assert state["money"] == MONEY_PLANTED


def test_apply_staged_marks_applied_not_saved(server, synthetic_save_path):
    """applyStaged writes the buffer: staged empties, appliedNotSaved=true,
    and the flag is driven by a real buffer-vs-disk difference."""
    server.result("openSave", {"path": str(synthetic_save_path)})
    server.result("setMoney", {"value": 555})

    state = server.result("applyStaged")
    assert state["money"] == 555
    assert state["staged"]["dirty"] is False
    assert state["staged"]["entries"] == []
    assert state["staged"]["appliedNotSaved"] is True

    # The flag reflects the disk, which still holds the planted value.
    assert SaveFile.load(synthetic_save_path).get_money() == MONEY_PLANTED


def test_save_with_backup_persists_and_backs_up(server, synthetic_save_path):
    """saveWithBackup: .bak appears; reopening the file through
    SaveFile.load shows the new money and valid integrity; state clean."""
    original_bytes = synthetic_save_path.read_bytes()
    server.result("openSave", {"path": str(synthetic_save_path)})
    server.result("setMoney", {"value": 999_999})

    result = server.result("saveWithBackup")
    assert result["savedPath"] == str(synthetic_save_path)
    backup = Path(result["backupPath"])
    assert backup.exists()
    assert backup.read_bytes() == original_bytes
    assert result["integrity"]["md5Ok"] is True

    reloaded = SaveFile.load(synthetic_save_path)
    assert reloaded.get_money() == 999_999
    assert reloaded.validate_integrity().md5_ok is True

    state = server.result("getState")
    assert state["staged"] == {
        "dirty": False,
        "appliedNotSaved": False,
        "entries": [],
    }


def test_over_cap_heat_is_blocked(server, synthetic_save_path):
    """setSlotHeat above the story cap -> BLOCKED error carrying the
    core's reason text; bytes untouched; an in-cap value then succeeds."""
    on_disk_before = synthetic_save_path.read_bytes()
    server.result("openSave", {"path": str(synthetic_save_path)})

    error = server.error("setSlotHeat", {"slotIndex": 0, "value": 5.0})
    assert error["data"]["errorCode"] == "BLOCKED"
    assert "locked by story progression" in error["message"]
    assert "x4" in error["message"]

    state = server.result("getState")
    assert state["staged"]["dirty"] is False
    assert synthetic_save_path.read_bytes() == on_disk_before

    staged = server.result("setSlotHeat", {"slotIndex": 0, "value": 4.0})["staged"]
    assert staged["entries"] == [
        {"field": "slot_heat", "slotIndex": 0, "have": HEAT_PLANTED, "want": 4.0}
    ]
    server.result("applyStaged")
    server.result("saveWithBackup")
    assert SaveFile.load(synthetic_save_path).get_slot_heat(0) == 4.0


def test_unknown_method_keeps_server_alive(server):
    """Unknown method -> -32601 error response; a following getState still
    answers (the loop never dies on bad input)."""
    error = server.error("definitelyNotAMethod")
    assert error["code"] == -32601

    state = server.result("getState")
    assert state["opened"] is False


def test_shutdown_exits_cleanly(server):
    """shutdown -> ok reply, process exit code 0, no orphan process."""
    result = server.result("shutdown")
    assert result == {"ok": True}
    assert server.proc.wait(timeout=5) == 0


def test_same_second_resave_reports_overwritten_backup(synthetic_save_path, monkeypatch):
    """Backup names are second-precision, so a same-second resave OVERWRITES
    the previous backup file. The service must report that backup, not fail
    with IO_ERROR because no new name appeared. In-process on purpose: the
    frozen backup path IS the same-second collision, deterministically."""
    fixed = synthetic_save_path.parent / (synthetic_save_path.name + ".bak_frozen")
    monkeypatch.setattr(SaveFile, "backup_path", lambda self: fixed)

    service = EditorService()
    service.open_save(str(synthetic_save_path))
    first = service.save_with_backup()
    assert Path(first.backup_path) == fixed
    second = service.save_with_backup()
    assert Path(second.backup_path) == fixed


def test_notification_is_processed_but_never_answered(server, synthetic_save_path):
    """JSON-RPC 2.0: a request without "id" is a notification — the server
    acts on it and MUST NOT reply. The next reply line must answer the next
    real request (the client below asserts on the response id)."""
    notification = {
        "jsonrpc": "2.0",
        "method": "openSave",
        "params": {"path": str(synthetic_save_path)},
    }
    server.proc.stdin.write(json.dumps(notification) + "\n")
    server.proc.stdin.flush()

    state = server.result("getState")
    assert state["opened"] is True  # the notification really was processed


def test_invalid_request_shape_is_rejected(server):
    """Missing "jsonrpc": "2.0" -> -32600 with the id echoed; a non-object
    request -> -32600 with id null; the loop survives both."""
    server.proc.stdin.write(json.dumps({"id": 7, "method": "getState"}) + "\n")
    server.proc.stdin.flush()
    response = json.loads(server.proc.stdout.readline())
    assert response["id"] == 7
    assert response["error"]["code"] == -32600

    server.proc.stdin.write(json.dumps(["getState"]) + "\n")
    server.proc.stdin.flush()
    response = json.loads(server.proc.stdout.readline())
    assert response["id"] is None
    assert response["error"]["code"] == -32600

    state = server.result("getState")
    assert state["opened"] is False


def test_string_numbers_are_rejected_by_the_strict_contract(server, synthetic_save_path):
    """The wire contract does not coerce: "123" is not a money value and
    "0" is not a slot index. JSON ints remain valid floats (a TS `number`
    serializes 4.0 as 4)."""
    server.result("openSave", {"path": str(synthetic_save_path)})

    error = server.error("setMoney", {"value": "123"})
    assert error["code"] == -32602
    assert error["data"]["errorCode"] == "INVALID_VALUE"

    error = server.error("setSlotHeat", {"slotIndex": "0", "value": 2.5})
    assert error["data"]["errorCode"] == "INVALID_VALUE"

    staged = server.result("setSlotHeat", {"slotIndex": 0, "value": 4})["staged"]
    assert staged["entries"][0]["want"] == 4.0
