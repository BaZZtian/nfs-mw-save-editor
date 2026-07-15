# NFS MW Save Editor

A Windows desktop save editor for **Need for Speed: Most Wanted (2005)** PC saves from the **v1.3 game executable**. Built with Python and PySide6.

NFS MW Save Editor has grown beyond its original Junkman inventory focus. It now covers profile values, Blacklist progress, garage placement, pursuit heat and bounty, performance tuning, and reusable car-build snapshots.

> **Release status:** the latest packaged build is [v1.4.0](https://github.com/sprintstate/nfs-mw-save-editor/releases/tag/v.1.4.0). This README documents the current `main` branch, which targets **v1.5.0** and includes development features that are not yet part of the stable download, most notably the Career dashboard and Change Rival workflow.

## Highlights

- Edit the 21 confirmed reward marker types used by the game
- Change profile alias and money
- Inspect Blacklist progress chapter by chapter
- Move cars between `Career` and `My Cars`
- Edit per-car pursuit bounty and story-capped heat
- Tune regular performance levels and Junkman parts
- Apply bundled or personal car builds to a save
- Preserve save integrity with backups, MD5 validation, and EA CRC32 repair
- Choose from 30 built-in UI themes

## Editor Pages

### Junkman

- View `Have` and stage new `Want` counts for all 21 confirmed marker types
- Filter Performance, Parts, Visual, and Bonus Marker rewards
- Use quick actions for complete reward categories
- Keep the practical 10-token cap or allow the maximum already supported by the current save
- Preserve invalid historical token data by default, with an explicit cleanup action in Settings

### Profile

- Edit Money
- Edit the ASCII profile alias with a conservative 7-character default
- Optionally unlock alias editing up to 16 characters
- Review Total Bounty, Escapes, Busts, Career cars, Pink Slips, My Cars, and free Career slots
- Show an optional save-integrity panel

### Career

The Career page is currently part of the v1.5.0 development branch.

- See the current Blacklist rival in a game-inspired hero dashboard
- Compare race wins, milestones, and bounty against chapter requirements
- Browse the full Blacklist timeline and inspect decoded race and milestone progress
- Resume from a different rival using a validated donor snapshot
- Choose between `Chapter Start` and `Boss Fight Ready` donor variants
- Preview exactly what changes and what remains yours before applying a stage

Career stage changes are staged in memory and do not touch the save on disk until `Save + backup` is used. Donor saves are not bundled with the repository or release; the Change Rival workflow only enables stages present in a validated local donor library.

### Garage

- Inspect resolved cars from both `Career` and `My Cars`
- Search by model and filter by source
- Move cars between `Career` and `My Cars` through allocator-checked actions
- Edit pursuit bounty and heat for linked Career cars
- Respect story progression when selecting heat levels
- See Pink Slip, active-car, parts-slot, and source status
- Optionally inspect reserved, reusable, placeholder, and blocked allocator slots

### Tuning

- Edit Career and My Cars builds in one place
- Set model-specific levels for Tires, Brakes, Suspension, Transmission, Engine, Turbo, and Nitrous
- Toggle confirmed Junkman performance categories
- Use `Max Performance`, `Max Junkman`, `Stock Build`, and `Clear Junkman`
- See Stock, Modified, Maxed, Junkman, and Read-only states
- Review decoded visual summaries where the current car data can be resolved
- Keep unknown or unsupported models read-only instead of guessing safe limits

### Builds

- Browse bundled Blacklist and bonus-car snapshots
- Maintain a personal `My Builds` library outside the application bundle
- Stage library builds into `My Cars` or `Career`
- Inspect builds already present in the open save
- Save a detected build to `My Builds`
- Export a complete build snapshot as JSON

External build JSON files can be added by placing valid snapshots in the `user_builds` directory. There is no separate `Import Snapshot...` button yet.

### Settings and About

- Switch between 30 built-in themes with live color previews
- Configure token limits, alias limits, integrity display, and allocator diagnostics
- Open the per-user token catalog directory
- Access legacy token preset import/export tools
- View the current application version, shortcuts, author credit, and GitHub link

## Safety Model

Save editing follows a staged workflow:

1. Controls update pending values only.
2. `Apply (memory)` writes those values to the in-memory save buffer.
3. `Save + backup` creates a timestamped `.bak`, repairs integrity data, and writes to disk.

Additional safeguards include:

- MD5 verification and repair for supported save layouts
- EA CRC32 validation for the three header blocks
- Stored file-size validation
- Planner-gated garage allocation and snapshot injection
- Story-based pursuit heat limits in both the UI and save layer
- Fail-closed behavior for unsupported layouts, unresolved tuning limits, and unsafe donor data

Keep a known-good copy of important saves even though the editor creates backups automatically.

## Download

Download the latest stable build from [GitHub Releases](https://github.com/sprintstate/nfs-mw-save-editor/releases/latest):

- **`NFS_MW_Junkman_Editor-onedir.zip`** - recommended portable build; extract the full archive and run the executable inside
- **`NFS_MW_Junkman_Editor.exe`** - standalone single-file build

Both builds are intended for Windows 10/11 and do not require a separate Python installation.

## Quick Start

1. Open a save with `Ctrl+O`, drag and drop it onto the window, or select `Open save`.
2. Make changes on the relevant page.
3. Review pending values and use `Apply (memory)`.
4. Use `Save + backup` to write the edited save to disk.
5. Keep the generated `.bak` until the edited save has been tested in game.

Shortcuts:

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Open save |
| `Ctrl+S` | Save with backup |
| `Ctrl+Z` | Reset pending values |

## Running From Source

Requirements:

- Windows
- Python 3.10 or newer
- PySide6 6.5 or newer

```powershell
git clone https://github.com/sprintstate/nfs-mw-save-editor.git
cd nfs-mw-save-editor

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\nfs_mw_save_editor\requirements.txt
.\.venv\Scripts\python.exe .\nfs_mw_save_editor\main.py
```

The packaged release is the right choice for normal use. Running from `main` is intended for development and testing of the next version.

## User Data

The application keeps personal data outside its installation directory:

| Data | Location |
| --- | --- |
| Token catalog | `%APPDATA%\NFS_MW_Junkman_Editor\token_catalog.json` |
| UI settings | `%APPDATA%\NFS_MW_Junkman_Editor\ui_settings.json` |
| Personal build library | `%APPDATA%\NFS_MW_Junkman_Editor\user_builds` |
| Career donor library | `%APPDATA%\NFS_MW_Junkman_Editor\career_ladder` |

Built-in car snapshots and icons are packaged with the application. Personal builds, donor saves, settings, and catalog overrides are not.

## Project Layout

```text
.
|-- README.md
|-- docs/                              # Public reverse-engineering notes
|-- nfs_mw_save_editor/
|   |-- main.py                        # Application entry point
|   |-- requirements.txt
|   |-- token_catalog.json             # Default 21-marker catalog
|   |-- assets/
|   |   |-- icons/                     # Original-game UI assets
|   |   `-- unique_cars/               # Bundled build snapshots
|   |-- core/
|   |   |-- savefile.py                # Save parser, editor, and integrity flow
|   |   |-- career_progress.py         # Blacklist progress decoding
|   |   |-- career_transplant.py       # Validated Change Rival workflow
|   |   |-- snapshot_library.py        # Build library discovery
|   |   |-- snapshot_injection.py      # Build placement planning and writes
|   |   |-- snapshot_export.py         # Complete build extraction
|   |   |-- junkman.py                 # Reward-marker inventory model
|   |   `-- visual_parts.py            # Decoded visual-part catalog
|   |-- ui/
|   |   |-- main_window.py             # Application shell and staged state
|   |   |-- theme.py                   # Theme presets and persisted UI settings
|   |   `-- pages/                     # Junkman, Profile, Career, Garage, Tuning, Builds
|   |-- tests/                         # Regression coverage
|   `-- release/                       # PyInstaller specifications
```

Developer-only assets and local release outputs are intentionally excluded from the public repository.

## Building Windows Packages

Install PyInstaller into the project environment, then run either specification from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller

# Portable folder build
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm .\nfs_mw_save_editor\release\spec\NFS_MW_Junkman_Editor.spec

# Standalone executable
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm .\nfs_mw_save_editor\release\onefile\spec_onefile\NFS_MW_Junkman_Editor.spec
```

Both specifications include the default token catalog, application icons, original-game UI assets, and bundled car snapshots.

## Reverse-Engineering Notes

The editor is based on validated save comparisons, game data, and in-game testing. Public technical notes live in:

- [`docs/JUNKMAN_OFFSETS.md`](docs/JUNKMAN_OFFSETS.md)
- [`docs/PROFILE_REVERSE_OVERVIEW.md`](docs/PROFILE_REVERSE_OVERVIEW.md)
- [`docs/PROFILE_REVERSE_NOTES.md`](docs/PROFILE_REVERSE_NOTES.md)
- [`docs/REVERSE_ENGINEERING_DOSSIER.md`](docs/REVERSE_ENGINEERING_DOSSIER.md)

The README intentionally stays at product level; byte offsets and research history belong in those documents.

## Disclaimer

This is an unofficial fan-made tool and is not affiliated with or endorsed by Electronic Arts.

Need for Speed and Need for Speed: Most Wanted are trademarks of Electronic Arts. Use the editor at your own risk and keep backups of important saves.
