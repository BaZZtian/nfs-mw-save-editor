# Add raw Xbox 360 / nfsmw-nx save support

Raw nfsmw-nx saves use the Xbox 360 layout: 62,688 bytes, big-endian numbers,
different bitfield/padding serialization and an eight-byte shift in the car
tables. Opening them with the PC layout misreads money, reward markers,
vehicles and integrity values.

This change detects the native MC02 format and translates its typed data
through the existing save-editing engine. The editor can read, edit and save
both PC and supported raw native files. This includes profile values, money,
reward markers, garage placement, tuning, car builds and career-stage changes,
with the staged Apply/Save workflow and automatic backups.

## Implementation

- Add `core/switch_format.py` for typed conversion and native persistence.
- Dispatch supported native input from `SaveFile` construction/loading.
- Normalize native input for the career dashboard and stage-byte reader.
- Preserve public native `data` and unknown bytes; repair native MD5 and
  three EA CRC32 fields on save.
- Add native regression tests, desktop integration checks and documentation.

Three existing backend files change and one backend module is added. Existing
PC editing behavior is retained. Platform-specific fields without a verified
mapping are retained rather than transplanted from PC.

The authoritative runtime payload is
`nfsmw/<XUID>/454107D9/00000001/<profile>/<profile>`. The port's
`saves/<profile>/actual` and `anterior` directories contain automatic copies
that rotate when a content container closes. Editing those copies does not
modify the file loaded by the game. The format documentation identifies the
correct payload and explains native integrity repair.

## Validation

- 203 existing non-Qt PC/API tests passed.
- 165 native-format tests passed, including an optional private raw-save
  fixture; the private fixture is not included.
- All 34 bundled builds tested in Career and My Cars, with save/reopen/export.
- All 30 bundled career stages tested in both bounty modes, with save/reopen.
- All 30 gameplay blocks passed byte-identical format round trips.
- Desktop integration passed open, eight-page navigation, Apply, Save + backup
  and disk reload with a temporary native-save copy.

The unmodified baseline Qt suite has two font/layout assertion failures in
the Linux offscreen test environment (359 other tests passed). Direct Windows
startup and game acceptance on Switch hardware have not been independently
verified. Packed Lua identifiers remain opaque; the validated key/value parser
rejects ambiguous payload boundaries. Support targets the documented raw
native layout, not STFS containers or every save version.

See [SWITCH_SAVE_FORMAT.md](SWITCH_SAVE_FORMAT.md) for schema evidence,
offsets, preservation rules, test commands and validation limits.
