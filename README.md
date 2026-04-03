# NFS Most Wanted 2005 - Save Editor

Desktop save editor for **Need for Speed: Most Wanted (2005)** on PC (`v1.3` saves).
Built with **Python 3** and **PySide6**.

The current app is no longer just a Junkman token editor. It now covers:
- Junkman inventory editing
- Profile alias and money editing
- Garage transfer management between `Career` and `My Cars`
- Tuning / parts editing for real car builds
- Build snapshot workflows through the `Builds` page
- Save integrity validation and checksum repair
- Multi-theme desktop UI with persisted settings

---

## Pages

### Junkman
- Edit all **22 token IDs**
- Search, category-filter, and rename catalog entries
- Use spinboxes, sliders, or quick unlock actions
- Compare `Have` vs `Want` in real time
- Track projected performance coverage with the footer progress bar
- Preserve unknown token data by default, or clear it intentionally through the safety flow

### Profile
- Edit **Money**
- Edit **Profile alias** with ASCII validation
- Default safe alias limit is **7** characters
- Optional unlock in Settings allows editing up to **16** characters
- Show save totals for **Total Bounty**, **Escapes**, and **Busts**
- Optional integrity panel can be shown on this page

### Garage
- Inspect real garage vehicles from the open save
- Filter by `All`, `Career`, or `My Cars`
- Move cars between `Career` and `My Cars`
- Edit bounty for pursuit-linked career cars
- See badges for source, pink-slip state, active car, parts slot, and raw location bits
- View allocator status (`Owned empty`, `Career empty`, `Blocked`)
- Optional pursuit diagnostics can be shown from Settings

### Tuning
- Edit tuning builds for both `Career` and `My Cars` in one place
- Filter by source and search by car model
- Bulk actions per card:
  - `Max Performance`
  - `Max Junkman`
  - `Stock Build`
  - `Clear Junkman`
- Per-category level editing and Junkman toggles
- Status badges reflect `Stock`, `Modified`, `Maxed`, `Junkman`, and `Read-only`
- Optional tuning diagnostics can be enabled directly on the page

### Builds
- Two views:
  - `Library`
  - `My Save`
- `Library` contains:
  - bundled built-in build snapshots from `assets/unique_cars`
  - optional personal snapshots from `%APPDATA%\NFS_MW_Junkman_Editor\user_builds`
- Library filters:
  - `Main`
  - `Bonus`
  - `User` (`My Builds`)
- Stage library builds into:
  - `My Cars`
  - `Career`
- `My Save` shows build snapshots detected in the currently opened save
- Save a detected build directly to `My Builds`
- Export a build snapshot as JSON

Note:
- External build JSON files are currently added by copying valid snapshot JSONs into the `My Builds` folder.
- There is no dedicated `Import Snapshot...` button yet.

### Settings and About
- Switch between multiple built-in theme presets
- Preview theme accent/background/foreground colors before leaving Settings
- Persist theme and UI preferences to `%APPDATA%`
- Open the token catalog folder directly from Settings
- Access legacy token preset import/export tools from `Settings -> Legacy Tools`
- About page shows app version, author credit, shortcut reference, and GitHub link

### Integrity, Save Flow, and UX
- Automatic **MD5** verification
- **EA CRC32** verification for the three header blocks
- File size validation against the stored header size
- One-click **Fix checksums**
- `Apply` updates the open save in memory
- `Save + backup` writes to disk and creates a `*.bak`
- `Ctrl+O`, `Ctrl+S`, `Ctrl+Z`
- Drag-and-drop save loading
- Toast notifications for non-blocking success feedback
- Scoped theme and page transition crossfades

---

## Data Locations

- Token catalog:
  - `%APPDATA%\NFS_MW_Junkman_Editor\token_catalog.json`
- UI settings:
  - `%APPDATA%\NFS_MW_Junkman_Editor\ui_settings.json`
- Personal build library:
  - `%APPDATA%\NFS_MW_Junkman_Editor\user_builds`
- Built-in bundled build library:
  - `nfs_mw_save_editor/assets/unique_cars`

Bundled `unique_cars` presets are included in both PyInstaller build modes:
- `onedir`
- `onefile`

Personal builds and UI settings stay outside the app bundle in `%APPDATA%`.

---

## Installation

### From source

```bash
# Clone the repo
git clone https://github.com/sprintstate/nfs-mw-save-editor.git
cd nfs-mw-save-editor/nfs_mw_save_editor

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux / macOS

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

### From release

Download the latest build from [Releases](https://github.com/sprintstate/nfs-mw-save-editor/releases).

Typical packaged variants:
- `onedir`: unpacked portable folder
- `onefile`: single executable

---

## Using The Editor

1. Open a save with `Ctrl+O`, drag-and-drop, or the `Open save` button.
2. Edit tokens on `Junkman`, money/alias on `Profile`, garage placement on `Garage`, and build levels on `Tuning`.
3. Use `Builds -> Library` to stage bundled or personal build snapshots into `Career` or `My Cars`.
4. Use `Builds -> My Save` to inspect builds already present in the save, save them into `My Builds`, or export them as JSON.
5. Click `Apply` to update the loaded save in memory.
6. Click `Save + backup` to write the modified save to disk.
7. If needed, use `Fix checksums` before saving or after changes.

Tips:
- The default token workflow is the practical capped mode. Enable the higher token-cap option in Settings only when you actually need it.
- Alias editing is intentionally conservative by default. If a save already contains a longer alias, unlock mode allows safe shortening up to 16 characters.
- External snapshot JSONs should be placed into `%APPDATA%\NFS_MW_Junkman_Editor\user_builds` to appear under `Builds -> Library -> My Builds`.

---

## Building Releases

PyInstaller spec files live in the repo and already include bundled app assets, including `assets/unique_cars`.

### `onedir`

```powershell
cd nfs_mw_save_editor
.venv\Scripts\python -m PyInstaller --noconfirm release\spec\NFS_MW_Junkman_Editor.spec
```

### `onefile`

```powershell
cd nfs_mw_save_editor
.venv\Scripts\python -m PyInstaller --noconfirm release\onefile\spec_onefile\NFS_MW_Junkman_Editor.spec
```

Specs:
- `release/spec/NFS_MW_Junkman_Editor.spec`
- `release/onefile/spec_onefile/NFS_MW_Junkman_Editor.spec`

---

## Project Structure

```text
save_editor_repo/
|-- README.md
|-- artifacts/                     # Local release outputs
|-- docs/                          # Reverse-engineering notes
|-- dev_assets/                    # Developer-only source assets / legacy files
`-- nfs_mw_save_editor/
    |-- main.py                    # Application entry point
    |-- resources.py               # Resource loader for source + PyInstaller
    |-- requirements.txt
    |-- token_catalog.json         # Default bundled token catalog
    |
    |-- assets/
    |   |-- icon.ico
    |   |-- icon.png
    |   |-- icons/                 # Token / nav / category icons
    |   `-- unique_cars/           # Bundled build snapshot library
    |       |-- blacklist/
    |       `-- bonus_cars/
    |
    |-- core/
    |   |-- savefile.py            # Main save parser/editor
    |   |-- models.py              # Shared dataclasses / typed models
    |   |-- tuning_limits.py       # Per-model tuning limits
    |   |-- cars.py                # Vehicle signature -> name mapping
    |   |-- junkman.py             # Token-slot detection / apply logic
    |   |-- checksums.py           # MD5 / EA CRC helpers
    |   |-- diff.py
    |   `-- patch.py
    |
    |-- ui/
    |   |-- main_window.py         # App shell and shared state
    |   |-- rendering.py           # Lazy card-grid rendering helpers
    |   |-- theme.py               # Theme presets + persisted UI settings
    |   |-- widgets.py             # Shared widgets / overlays / toasts
    |   `-- pages/
    |       |-- junkman_mixin.py
    |       |-- profile_mixin.py
    |       |-- garage_mixin.py
    |       |-- parts_mixin.py
    |       |-- presets_mixin.py
    |       |-- settings_mixin.py
    |       `-- constants.py
    |
    `-- release/
        |-- spec/
        |   `-- NFS_MW_Junkman_Editor.spec
        `-- onefile/
            `-- spec_onefile/
                `-- NFS_MW_Junkman_Editor.spec
```

Notes:
- `docs/` contains reverse-engineering notes and is not part of runtime packaging.
- `dev_assets/` contains developer-only assets and archived helpers.
- `artifacts/` is for locally assembled release outputs and preview builds.

---

## Save Format Notes

### Header and integrity

| Offset | Size | Description |
|--------|------|-------------|
| `0x00` | 4 | Magic: `MC02` |
| `0x04` | 4 | File size (LE) |
| `0x10` | 4 | CRC block 1 |
| `0x14` | 4 | CRC data |
| `0x18` | 4 | CRC block 2 |
| `0x34` | ... | Saved data start |
| tail 16 | 16 | MD5 hash |

### Junkman slot layout

Each detected token slot uses a `0x0C`-byte stride:

| Byte | Description |
|------|-------------|
| `+0x00` | Token type ID (`1..22` are the currently supported valid IDs) |
| `+0x01..0x07` | Padding |
| `+0x08` | Count (`1` for filled, `0` for empty in the raw slot layout) |
| `+0x09..0x0B` | Padding |

### Profile / Rap Sheet notes

- Profile alias is stored in a fixed ASCII buffer at `0x5A31`.
- The raw alias buffer is `0x24` bytes, but the editor intentionally applies safer product limits:
  - default safe edit limit: `7`
  - optional unlocked edit limit: `16`
- Money is stored as a fixed `u32`.
- Bounty / escape / bust summaries are derived from the detected pursuit-linked garage records.
- Vehicle names are resolved by matching career signatures against the known dictionary in `core/cars.py`.

For deeper reverse-engineering notes, see:
- `docs/JUNKMAN_OFFSETS.md`
- `docs/PROFILE_REVERSE_NOTES.md`
- `docs/PROFILE_REVERSE_OVERVIEW.md`

---

## Requirements

- **Python** >= 3.10
- **PySide6** >= 6.5

---

## License

This project is provided as-is for educational and personal use.
Need for Speed: Most Wanted is a trademark of Electronic Arts.
