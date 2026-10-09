# NFS MW Save Editor — Historical Switch Preview

**Superseded pre-review snapshot.** Current community source is on
[main](https://github.com/BaZZtian/nfs-mw-save-editor/tree/main).
Use [Preview 2](https://github.com/BaZZtian/nfs-mw-save-editor/releases/tag/v1.5.0-switch-preview.2)
for the current experimental community download. Official builds are available
from [sprintstate’s releases](https://github.com/sprintstate/nfs-mw-save-editor/releases).


A Windows desktop save editor for **Need for Speed: Most Wanted (2005)** PC saves from the **v1.3 game executable** and raw Xbox 360 saves used by the **nfsmw-nx Switch port**. Built with Python and PySide6.

Raw Xbox 360 / nfsmw-nx support targets the documented 62,688-byte MC02 layout. It is currently a preview; game acceptance on Switch hardware has not been independently verified. See [the save-format documentation](docs/SWITCH_SAVE_FORMAT.md) for supported layouts, the authoritative save path and validation.

NFS MW Save Editor has grown beyond its original Junkman inventory focus. It now covers profile values, Blacklist progress, garage placement, pursuit heat and bounty, performance tuning, and reusable car-build snapshots.

> **Historical Switch preview:** `v1.5.0-switch-preview.1` is superseded by [Preview 2](https://github.com/BaZZtian/nfs-mw-save-editor/releases/tag/v1.5.0-switch-preview.2).
>
> **Latest upstream release:** [v1.5.0](https://github.com/sprintstate/nfs-mw-save-editor/releases/tag/v1.5.0), featuring the Career dashboard, Change Rival workflow, safer build injection, and a redesigned staged-save experience.

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

## Switch save files

Open the raw save payload at `nfsmw/<XUID>/454107D9/00000001/<profile>/<profile>` inside your nfsmw-nx installation. Use the profile and XUID folders created by your installation; the final component is a file without an extension.

The `saves/<profile>/actual` and `anterior` directories contain automatic copies. Edit the authoritative payload above so the game loads your changes. Close the game completely before editing the SD card, use `Apply (memory)` followed by `Save + backup`, and reopen the saved file to check the values.

See [SWITCH_SAVE_FORMAT.md](docs/SWITCH_SAVE_FORMAT.md) for format detection, integrity handling and validation limits.

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

- See the current Blacklist rival in a game-inspired hero dashboard
- Compare race wins, milestones, and bounty against chapter requirements
- Browse the full Blacklist timeline and inspect decoded race and milestone progress
- Resume from a different rival using a validated donor snapshot
- Choose between `Chapter Start` and `Boss Fight Ready` donor variants
- Preview exactly what changes and what remains yours before applying a stage

Career stage changes are staged in memory and do not touch the save on disk until `Save + backup` is used. The release includes 30 validated compact progression snapshots, covering both variants for all 15 rivals. Full donor saves and donor profile identity are not bundled.

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
- View the current application version, shortcuts, author credit, GitHub link, and third-party licenses

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

Download the [Windows portable Switch support preview](https://github.com/BaZZtian/nfs-mw-save-editor/releases/download/v1.5.0-switch-preview.1/NFS_MW_Junkman_Switch_PC_1.5.0.zip): **`NFS_MW_Junkman_Switch_PC_1.5.0.zip`**. Extract the complete ZIP and run `NFS_MW_Junkman_Editor.exe`; keep the `_internal` folder beside the executable. No separate Python installation is required.

The release notes are available on the [preview release page](https://github.com/BaZZtian/nfs-mw-save-editor/releases/tag/v1.5.0-switch-preview.1).

### Upstream PC release

The upstream stable PC build is available from [GitHub Releases](https://github.com/sprintstate/nfs-mw-save-editor/releases/latest):

- **`NFS_MW_Junkman_Editor.exe`** - recommended standalone single-file build
- **`NFS_MW_Junkman_Editor_onedir.zip`** - portable folder build; extract the full archive and run the executable inside

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

The packaged release is the right choice for normal use. Running from source is intended for development and testing.

## User Data

The application keeps personal data outside its installation directory:

| Data | Location |
| --- | --- |
| Token catalog | `%APPDATA%\NFS_MW_Junkman_Editor\token_catalog.json` |
| UI settings | `%APPDATA%\NFS_MW_Junkman_Editor\ui_settings.json` |
| Personal build library | `%APPDATA%\NFS_MW_Junkman_Editor\user_builds` |

Built-in car snapshots, compact Career progression snapshots, and icons are packaged with the application. Personal builds, full donor saves, settings, and catalog overrides are not.

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
|   |   |-- career_stages/              # Bundled Change Rival snapshots
|   |   |-- icons/                     # Runtime-ready original-game UI assets
|   |   `-- unique_cars/               # Bundled build snapshots
|   |-- core/
|   |   |-- savefile.py                # Save parser, editor, and integrity flow
|   |   |-- switch_format.py           # Raw Xbox 360 / nfsmw-nx format adapter
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

Full-resolution source layers, other developer-only assets, and local release outputs are intentionally excluded from the public repository and packaged application.

## Building Windows Packages

Install PyInstaller into the project environment, then run either specification from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller

# Portable folder build
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm .\nfs_mw_save_editor\release\spec\NFS_MW_Junkman_Editor.spec

# Standalone executable
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm .\nfs_mw_save_editor\release\onefile\spec_onefile\NFS_MW_Junkman_Editor.spec
```

Both specifications include the default token and visual-parts catalogs, application icons, runtime-ready original-game UI assets, bundled car snapshots, all 30 compact Career progression snapshots, Windows version metadata, and the third-party license bundle. Full-resolution source layers, unused image variants, and unused Qt modules and plugins are explicitly excluded.

## Third-party software

The packaged application includes Python, Qt/PySide6, NumPy, and the PyInstaller bootloader. Their notices and license texts are listed in [`nfs_mw_save_editor/THIRD_PARTY_NOTICES.md`](nfs_mw_save_editor/THIRD_PARTY_NOTICES.md) and bundled with each package. The application's About page presents a concise native summary, official project links, and an in-app viewer for every bundled license text. The Qt notice provides direct network access to the exact corresponding-source archives under GPLv3 section 6(d), plus relinking information for the dynamically linked LGPL components.

## Reverse-Engineering Notes

The editor is based on validated save comparisons, game data, and in-game testing. Public technical notes live in:

- [`docs/JUNKMAN_OFFSETS.md`](docs/JUNKMAN_OFFSETS.md)
- [`docs/PROFILE_REVERSE_OVERVIEW.md`](docs/PROFILE_REVERSE_OVERVIEW.md)
- [`docs/PROFILE_REVERSE_NOTES.md`](docs/PROFILE_REVERSE_NOTES.md)
- [`docs/REVERSE_ENGINEERING_DOSSIER.md`](docs/REVERSE_ENGINEERING_DOSSIER.md)
- [`docs/SWITCH_SAVE_FORMAT.md`](docs/SWITCH_SAVE_FORMAT.md)

The README intentionally stays at product level; byte offsets and research history belong in those documents.

## Disclaimer

This is an unofficial fan-made tool and is not affiliated with or endorsed by Electronic Arts.

Need for Speed and Need for Speed: Most Wanted are trademarks of Electronic Arts. Use the editor at your own risk and keep backups of important saves.
