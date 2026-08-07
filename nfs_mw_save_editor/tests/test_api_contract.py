"""Contract tests for the web-UI boundary (`nfs_mw_save_editor.api`).

These tests exercise the REAL process boundary: they spawn
`python -m api.server` (cwd = nfs_mw_save_editor/) as a subprocess and speak
newline-delimited JSON-RPC over its stdio — no in-process shortcuts, so a
green run certifies exactly what the Electron shell will use.

Fixture save: synthetic, built on the pattern of
`test_apply_belt_sentinel._make_savefile` (full-size 0xF86C buffer) but
written to a tmp file with `fix_integrity()` applied, plus one planted
career car (owned record + pursuit record + money + alias) so Profile and
Garage state have something real to assert against. No personal saves.

STAGE A SCAFFOLD: every test body is a skip; names + docstrings pin the
acceptance list. Implementation fills the bodies without renaming tests.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def synthetic_save_path(tmp_path):
    """Full-size synthetic save on disk: valid integrity, known money,
    alias, one career car with known bounty/heat, story rank set so the
    heat cap is x4 (rank 5..8) — the over-cap test needs headroom to 5."""
    pytest.skip("stage A scaffold")


@pytest.fixture
def server(synthetic_save_path):
    """Spawned api.server subprocess + a tiny NDJSON JSON-RPC client;
    guarantees shutdown/kill in teardown so no orphan survives a red run."""
    pytest.skip("stage A scaffold")


def test_hello_handshake(server):
    """hello returns PROTOCOL_VERSION and the running sys.executable."""
    pytest.skip("stage A scaffold")


def test_open_save_state_matches_planted_bytes(server, synthetic_save_path):
    """openSave returns SaveState whose alias/money/garage mirror exactly
    what the fixture planted; opening modifies nothing on disk."""
    pytest.skip("stage A scaffold")


def test_staged_money_reset_roundtrip(server):
    """setMoney stages (dirty=true, entry have->want); resetStaged returns
    a clean state; the save buffer bytes never changed."""
    pytest.skip("stage A scaffold")


def test_apply_staged_marks_applied_not_saved(server):
    """applyStaged writes the buffer: staged empties, appliedNotSaved=true,
    and the flag is driven by a real buffer-vs-disk difference."""
    pytest.skip("stage A scaffold")


def test_save_with_backup_persists_and_backs_up(server, synthetic_save_path):
    """saveWithBackup: .bak appears; reopening the file through
    SaveFile.load shows the new money and valid integrity; state clean."""
    pytest.skip("stage A scaffold")


def test_over_cap_heat_is_blocked(server):
    """setSlotHeat above the story cap -> BLOCKED error carrying the
    core's reason text; bytes untouched; an in-cap value then succeeds."""
    pytest.skip("stage A scaffold")


def test_unknown_method_keeps_server_alive(server):
    """Unknown method -> -32601 error response; a following getState still
    answers (the loop never dies on bad input)."""
    pytest.skip("stage A scaffold")


def test_shutdown_exits_cleanly(server):
    """shutdown -> ok reply, process exit code 0, no orphan process."""
    pytest.skip("stage A scaffold")
