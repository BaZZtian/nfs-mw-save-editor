# NFS MW (2005) Save Editor - Reverse Engineering Dossier

Target save format: PC 63,596 bytes.

## 1. Minimal Data Model
The fundamental entities in the save file around which the editor should be built:

```python
# Layer A - Car Identity
class CarRecord:
    save_index: int       # numbering
    signature: bytes      # 8-byte car type signature
    location_bits: int    # 01=stock, 02=career, 04=mycars, 20=special, 40=pink slips
    misc_bits: int
    parts_slot: int       # link to parts section
    career_slot: int      # link to pursuit record
    
# Layer B - Rap Sheet / Pursuit Stats
class PursuitRecord:
    bounty: int
    escaped: int
    busted: int
    # ...future: fines / infractions / total pursuit stats

# Layer UI - Resolved Entity
class ResolvedVehicleEntry:
    car_record: CarRecord
    pursuit_record: PursuitRecord  # joined via career_slot
    resolved_model_name: str
    confidence: float
```

## 2. Confirmed Facts
- **Car Identity Block (`0x6219`)**: Contains 0x14-byte records representing owned cars. Includes numbering, an 8-byte car type signature, location bits, parts-slot, career-slot, and a `CD CD...` padding/marker.
- **Pursuit/Rap Sheet Block (`0xE2ED`)**: Contains 0x38-byte records for per-car statistics. Features `bounty` (u32 at +0x10), `escaped` (u16 at +0x14), and `busted` (u16 at +0x16). Total bounty/escapes in the game UI are dynamic sums of these per-car records.
- **Record Linkage**: The `career_slot` in the Car Identity block explicitly links to the index in the Pursuit block.
- **Location Bits**: Validated legacy flags: `01` = stock, `02` = career, `04` = mycars, `0x20` = special cars, `0x40` = pink slips.

## 3. Likely to Work (Safe Features)
- **Garage Manager v1**: Reading real cars via signature, displaying location/parts/career slots, and linking to Rap Sheet. Safe operations include viewing, renaming/identifying, toggling visibility based on valid bits, and safe editing of pursuit stats.
- **Parts Editor v1 (Safe Mode)**: Reading existing performance/unique parts (Tires, Brakes, Suspension, Transmission, Engine, Turbo/Supercharger, NOS). Unique upgrades are a bitmask (`0x7F` = all unique). Safe operations: view, copy build to compatible cars, restricted editing.

## 4. Unknowns & Risky Operations
- **Full Parts Section Layout**: The parts-slot pointer is known, but creating a car "from scratch" is risky because the game needs a well-formed parts section.
- **Identity Block Unknowns**: Exact meaning of all flags in `+0x0C` and `+0x0E`.
- **Current Car Field**: Very tricky. Historical CE trainers rely heavily on memory pointers that change during runtime (free roam, car list scroll). A stable save-level anchor for "current car" is still unknown.
- **Unlocks (Cars/Parts/Progression)**: Legacy methods mostly relied on runtime memory patching.

## 5. Next Step Targets (Roadmap)
1.  **Resolver Layer Finalization**: `signature -> model`, `career_slot -> linked pursuit record`.
2.  **Garage Manager v1**: Read real cars, names, linked Rap Sheet, location flags. Implement UI for safe viewing, sorting, and flagging.
3.  **Parts Viewer/Editor v1**: Expose `parts-slot`, read existing upgrades, implement safe cloning between compatible models.
4.  **Defer**: Creating cars from scratch, current-car switching, Blacklist/Milestones editing (until solid file-level anchors are found).
