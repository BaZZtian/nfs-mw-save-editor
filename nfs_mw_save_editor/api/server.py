"""JSON-RPC 2.0 server over stdio — the process boundary.

Framing: one JSON-RPC message per line (newline-delimited), UTF-8.
stdout carries protocol frames ONLY — a single stray print would corrupt
the stream, so all logging goes to stderr via the `logging` module.

Method table (wire names are camelCase; params/results are the schema
models, validated on entry):

    hello           -> HelloResult      (no params; always available)
    openSave        OpenSaveParams -> SaveState
    getState        -> SaveState
    setMoney        SetMoneyParams -> SaveState
    setSlotHeat     SetSlotHeatParams -> SaveState
    resetStaged     -> SaveState
    applyStaged     -> SaveState
    saveWithBackup  -> SaveResult
    closeSave       -> SaveState
    shutdown        -> {"ok": true}, then clean exit 0

Error contract: ApiError maps to a JSON-RPC error object using
schema.JSONRPC_ERROR_CODES; `error.data.errorCode` carries the ApiErrorCode
string so clients switch on names, not numbers. Unknown method -> standard
-32601; malformed JSON line -> -32700 with id null. The loop catches
everything: bad input NEVER kills the process — only `shutdown` (or EOF on
stdin, which means the parent died) ends it.

Entry point: `python -m api.server`, run with `nfs_mw_save_editor/` as the
working directory — same top-level package layout (`core`, `ui`, `api`) the
rest of the app uses.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, Optional

from . import PROTOCOL_VERSION
from .service import ApiError, EditorService


def _hello_result() -> Dict[str, Any]:
    """protocol_version + sys.executable (venv sanity, known gotcha)."""
    raise NotImplementedError("stage A scaffold")


def dispatch(service: EditorService, method: str, params: Optional[dict]) -> Any:
    """Route one request: validate params via the schema model, call the
    service, dump the result model by alias (camelCase). Raises ApiError /
    KeyError for the loop to translate; never writes to stdout itself."""
    raise NotImplementedError("stage A scaffold")


def serve(stdin=None, stdout=None) -> int:
    """Blocking read-dispatch-respond loop; returns the process exit code.

    Injectable streams keep the loop unit-testable in-process, while the
    contract tests still exercise the real subprocess path.
    """
    raise NotImplementedError("stage A scaffold")


def main() -> int:
    """Configure stderr logging, then serve() on the real stdio."""
    raise NotImplementedError("stage A scaffold")


if __name__ == "__main__":
    sys.exit(main())
