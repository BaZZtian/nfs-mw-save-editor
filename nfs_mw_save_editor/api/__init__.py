"""Web-UI backend boundary for the NFS MW save editor.

This package exposes the tested Python core (`core/`) to an external UI
process over a typed JSON-RPC contract. It never imports Qt and never
re-derives save-format rules: every game rule resolves through core calls.

Protocol versioning: bump PROTOCOL_VERSION on any wire-visible change
(method added/removed, model field changed). The frontend checks it in the
`hello` handshake and must refuse to run on a mismatch.
"""

PROTOCOL_VERSION = "0.1.0"
