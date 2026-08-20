"""JSON-RPC 2.0 server over stdio: the process boundary.

Framing: one JSON-RPC message per line (newline-delimited), UTF-8.
stdout carries protocol frames ONLY; a single stray print would corrupt
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
string so clients switch on names, not numbers. Pydantic param validation
failures map to the standard -32602 (invalid params) with
errorCode=INVALID_VALUE. Unknown method -> standard -32601; malformed JSON
line -> -32700 with id null. Request errors are isolated to their response;
only `shutdown` or stdin EOF ends the process.

Entry point: `python -m api.server`, run with `nfs_mw_save_editor/` as the
working directory: the same top-level package layout (`core`, `ui`, `api`) the
rest of the app uses.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

from pydantic import ValidationError

from . import PROTOCOL_VERSION
from .schema import (
    JSONRPC_ERROR_CODES,
    ApiErrorCode,
    HelloResult,
    OpenSaveParams,
    SetMoneyParams,
    SetSlotHeatParams,
)
from .service import ApiError, EditorService

logger = logging.getLogger("api.server")


def _hello_result() -> Dict[str, Any]:
    """Return the protocol version and active Python executable."""
    return HelloResult(
        protocol_version=PROTOCOL_VERSION, python_exe=sys.executable
    ).model_dump(by_alias=True)


def dispatch(service: EditorService, method: str, params: Optional[dict]) -> Any:
    """Validate and dispatch one request without writing to stdout."""
    p = params or {}
    if method == "hello":
        return _hello_result()
    if method == "openSave":
        return service.open_save(OpenSaveParams.model_validate(p).path).model_dump(by_alias=True)
    if method == "getState":
        return service.get_state().model_dump(by_alias=True)
    if method == "setMoney":
        args = SetMoneyParams.model_validate(p)
        return service.set_money(args.value).model_dump(by_alias=True)
    if method == "setSlotHeat":
        args = SetSlotHeatParams.model_validate(p)
        return service.set_slot_heat(args.slot_index, args.value).model_dump(by_alias=True)
    if method == "resetStaged":
        return service.reset_staged().model_dump(by_alias=True)
    if method == "applyStaged":
        return service.apply_staged().model_dump(by_alias=True)
    if method == "saveWithBackup":
        return service.save_with_backup().model_dump(by_alias=True)
    if method == "closeSave":
        return service.close_save().model_dump(by_alias=True)
    raise KeyError(method)


def _write(stdout, payload: Dict[str, Any]) -> None:
    stdout.write(json.dumps(payload) + "\n")
    stdout.flush()


def serve(stdin=None, stdout=None) -> int:
    """Blocking read-dispatch-respond loop; returns the process exit code.

    Injectable streams keep the loop unit-testable in-process, while the
    contract tests still exercise the real subprocess path.
    """
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    service = EditorService()

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write(stdout, {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            })
            continue

        # JSON-RPC 2.0 shape gate: an invalid Request object is answered
        # with -32600 (id echoed when one was readable, else null).
        if (
            not isinstance(message, dict)
            or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
        ):
            _write(stdout, {
                "jsonrpc": "2.0",
                "id": message.get("id") if isinstance(message, dict) else None,
                "error": {"code": -32600, "message": "invalid request"},
            })
            continue

        # A request without "id" is a notification: process it, respond
        # never, not even with an error (per spec).
        is_notification = "id" not in message
        response: Dict[str, Any] = {"jsonrpc": "2.0", "id": message.get("id")}
        method = message["method"]
        params = message.get("params")

        if method == "shutdown":
            if not is_notification:
                response["result"] = {"ok": True}
                _write(stdout, response)
            logger.info("shutdown requested, exiting")
            return 0

        try:
            response["result"] = dispatch(service, method, params)
        except KeyError:
            response["error"] = {
                "code": -32601,
                "message": f"unknown method {method!r}",
            }
        except ValidationError as exc:
            response["error"] = {
                "code": -32602,
                "message": str(exc),
                "data": {"errorCode": ApiErrorCode.INVALID_VALUE.value},
            }
        except ApiError as exc:
            response["error"] = {
                "code": JSONRPC_ERROR_CODES[exc.code],
                "message": exc.message,
                "data": {"errorCode": exc.code.value},
            }
        except Exception as exc:  # the loop must survive anything
            logger.exception("internal error handling %r", method)
            response["error"] = {
                "code": JSONRPC_ERROR_CODES[ApiErrorCode.INTERNAL],
                "message": f"{type(exc).__name__}: {exc}",
                "data": {"errorCode": ApiErrorCode.INTERNAL.value},
            }
        if not is_notification:
            _write(stdout, response)

    logger.info("stdin closed, exiting")
    return 0


def main() -> int:
    """Configure stderr logging, then serve() on the real stdio."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    return serve()


if __name__ == "__main__":
    sys.exit(main())
