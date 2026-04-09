# Profile reverse notes (PC v1.3)

These notes document how the Profile / Rap Sheet car data was reverse-engineered for
NFS Most Wanted (2005) PC v1.3 saves (`63,596` bytes).

Main reference saves used during validation:
- `Save1`
- `Save2`
- `fixture-c`

Forum reference:
- old Cheat Engine threads with the car list and save-structure hints

## Goal

Find a reliable way to resolve:
- per-car `Bounty`
- per-car `Escaped`
- per-car `Busted`
- real vehicle name for each Profile garage card

without guessing from a fake enum or UI order.

## Step 1: confirm the pursuit / bounty block

The first confirmed block was the per-car pursuit block:

- base: `0xE2ED`
- stride: `0x38`

Record layout:
- `+0x10` -> `u32 bounty`
- `+0x14` -> `u16 escaped`
- `+0x16` -> `u16 busted`

Detection invariants used in code:
- bytes `1:4 == CD 03 00`
- bytes `8:12 == 00 00 CD CD`

Observed results:
- `Save1`: `13` valid records, total bounty `12,190,486`
- `Save2`: `17` valid records, total bounty `14,926,350`
- `fixture-c`: `7` valid records, total bounty `200,150`

This block is the source of truth for:
- bounty editing
- escaped total
- busted total
- computed total bounty / rating

## Step 2: reject the fake global bounty idea

An earlier hypothesis treated a single global field as the main bounty source.
That did not hold up on real saves.

The decisive clue was:
- summing `+0x10` across valid pursuit records matched the in-game total bounty

This made the correct model:
- total bounty is derived from per-car pursuit records
- writes should target the pursuit record, not a separate global total field

## Step 3: find the real car identity block

The second major breakthrough was a separate career vehicle block:

- base: `0x6219`
- stride: `0x14`

Record layout:
- `+0x00` -> `u32 car number`
- `+0x04` -> `8-byte car signature`
- `+0x0C` -> `u16 flags`
- `+0x0E` -> `u16 flags2 / unknown`
- `+0x10` -> `u8 parts slot`
- `+0x11` -> `u8 career slot`
- `+0x12` -> `CD CD`

Important behavior:
- the block is larger than the active car list
- active records are at the front
- the tail is filler:
  - `car number = 0xFFFFFFFF`
  - signature = `00 00 00 00 00 00 00 00`
  - `career_slot = 0xFF`

Active record filter:
- `car_number != 0xFFFFFFFF`
- signature is not all zeroes
- `career_slot != 0xFF`

Observed results:
- `fixture-a`: `13` active car records
- `fixture-b`: `17` active car records

## Step 4: link both layers through `career_slot`

The key relation is:

`career vehicle record.career_slot == pursuit record index`

In practice:
- read active car records from `0x6219`
- read pursuit records from `0xE2ED`
- join them by `career_slot`

This matched cleanly on the validation saves.

Examples from `Save2`:
- slot `0` -> `Chevrolet Cobalt SS` -> bounty `9,427,250`
- slot `1` -> `VW Golf GTI` -> bounty `29,950`
- slot `2` -> `Lexus IS300` -> bounty `51,750`
- slot `10` -> `Lamborghini Gallardo` -> bounty `270,550`
- slot `15` -> `BMW M3 GTR` -> bounty `2,390,000`

Examples from `Save1`:
- slot `0` -> `Chevrolet Cobalt SS`
- slot `7` -> `Lamborghini Gallardo`
- slot `12` -> `Mercedes SLR McLaren`

This is the relation now used by the editor.

## Step 5: resolve car names by exact 8-byte signature

Vehicle names are resolved by exact signature match, not by the old temporary `car_id`
display and not by a hand-made small enum.

Resolver rule:
- exact `8-byte signature -> model name`

Examples:
- `95 40 78 5A 95 40 78 5A` -> `Chevrolet Cobalt SS`
- `34 34 F1 66 34 34 F1 66` -> `Toyota Supra`
- `0B C4 2C 7B 0B C4 2C 7B` -> `Lamborghini Gallardo`
- `92 99 86 C4 D4 3D 06 67` -> `Porsche Carrera GT`
- `BB D9 2A E3 BB D9 2A E3` -> `Mercedes SLR McLaren`
- `4E 4A CC 23 B3 5F 08 4E` -> `BMW M3 GTR`

The forum car list was used as the initial source, then checked against real save data.

## Step 6: confirmed parts block behind `parts_slot`

The earlier `0x55E4 + parts_slot * 0x0C` candidate turned out to be a false lead for
installed parts. Controlled A/B saves with a stock Fiat Punto and one-part-only
upgrades disproved it.

The confirmed save-level build structure is:

- block base: `0x9CCD`
- block stride: `0x198`
- addressing rule: `block_abs_off = 0x9CCD + (parts_slot - 31) * 0x198`
- end marker at `+0x194..+0x197`: `<parts_slot> CD CD CD`

This formula validates on `fixture-a`, `fixture-b`, `fixture-c`, and `fixture-d`.

### Confirmed decoded fields

Inside each parts block, the currently confirmed offsets are:

- `+0x118` -> Tires level
- `+0x11C` -> Brakes level
- `+0x120` -> Suspension level
- `+0x124` -> Transmission level
- `+0x128` -> Engine level
- `+0x12C` -> Turbo/Supercharger level
- `+0x130` -> NOS level
- `+0x134` -> Junkman / unique-parts bitmask

These fields behave as little-endian `u32`, even when only the low byte changes in
practice.

### Confirmed Fiat experiments

Using `fixture-a(stock fiat)` as the baseline for `parts_slot 55`:

- `only race engine` -> `+0x128 = 01`
- `only pro engine` -> `+0x128 = 02`
- `only super pro engine` -> `+0x128 = 03`
- `only ultimate engine` -> `+0x128 = 04`

This confirms the engine ladder `00 / 01 / 02 / 03 / 04` for that category.

Single-upgrade Ultimate saves confirmed the per-category offsets:

- `ultimate tires` -> `+0x118 = 03`
- `ultimate brakes` -> `+0x11C = 04`
- `ultimate suspension` -> `+0x120 = 03`
- `ultimate transmission` -> `+0x124 = 04`
- `ultimate turbo` -> `+0x12C = 03`
- `ultimate nos` -> `+0x130 = 03`

The different maximum values strongly suggest category-specific level caps, even
though the storage format is shared.

### Confirmed Junkman mask

The Junkman field at `+0x134` is now fully confirmed as a bitmask:

- `0x01` -> Tires
- `0x02` -> Brakes
- `0x04` -> Suspension
- `0x08` -> Transmission
- `0x10` -> Engine
- `0x20` -> Turbo
- `0x40` -> NOS
- `0x7F` -> full set

This was validated with single-part Junkman saves and the required gated tests:

- `ultimate turbo + junkman turbo` -> adds only `0x20`
- `ultimate nos + junkman nos` -> adds only `0x40`

### What is still not claimed

- exact human-facing shop labels for every numeric level on every category
- whether all cars share the same max tier count per category
- the meaning of the rest of the `0x198` block outside the confirmed decoded window

## Step 7: confirmed visual build layer

Visual-only save diffs on `fixture-a(visual_base)` confirmed that visual tuning does not
live in the pursuit block and does not depend on `career_slot`.

The primary visual layer lives inside the same `parts_slot`-keyed `0x198` build block
already used for performance.

### Confirmed primary visual offsets

For the tested `Lexus IS300` My Cars build (`parts_slot 45`), the following offsets
inside the primary build block were isolated by single-change visual saves:

- `+0x02E` -> body kit
- `+0x058..+0x059` -> spoiler
- `+0x07C` -> roof
- `+0x07E` -> hood
- `+0x084..+0x085` -> rims
- `+0x098` -> paint selector family
- `+0x09A..+0x09B` -> body vinyl
- `+0x09C..+0x09D` -> advanced visual / sidecar pointer candidate
- `+0x0A6..+0x0A7` -> windshield decal
- `+0x0B6..+0x0B7` -> rear-window decal
- `+0x0D0..+0x0D1` -> left-door decal slot
- `+0x0D2..+0x0D5` -> number visual half A
- `+0x0E0..+0x0E1` -> right-door decal slot
- `+0x0E2..+0x0E5` -> number visual half B
- `+0x0E6..+0x0E7` -> left-quarter decal
- `+0x0F6..+0x0F7` -> right-quarter decal
- `+0x106` -> window tint
- `+0x108`, `+0x10A`, `+0x10C`, `+0x10E` -> custom gauge cluster

Combined saves behave as a set union in this primary block. For example,
`left-door decal + rear-window decal` changes exactly the union of the two individual
offset sets.

### Optional advanced-visual sidecar

Advanced visual edits can also claim an adjacent auxiliary pair:

1. the next car-identity record after the primary My Cars car
2. the next parts block at `parts_slot + 1`

Observed on `fixture-a(visual_base)` and its variants:

- primary car: `Lexus IS300`, `parts_slot 45`
- adjacent sidecar record at `0x6331`
- sidecar build block at `0xB4B5` (`parts_slot 46`)

When this sidecar is active:

- the adjacent record keeps:
  - `car_number = 0xFFFFFFFF`
  - `location_bits = 0x04`
  - `career_slot = 0xFF`
- but its `8-byte signature` flips to the same signature as the primary car
- the adjacent build block becomes part of the effective visual payload

Important nuance:

- the sidecar block keeps the placeholder marker `FF CD CD CD`
- it does **not** rewrite the marker to `<parts_slot> CD CD CD`

The current extractor therefore validates the primary block strictly, but allows the
placeholder marker on the optional sidecar block.

### Unresolved external table near `0x5577`

Many visual saves also flip a 57-entry table near `0x5577`:

- `57` entries
- stride `0x08`
- each entry is now treated as a full `8-byte` record, not a single-byte value
- the old byte-`+0` probe is preserved only as legacy/debug output
- the new primary reverse focus is byte `+4` inside each 8-byte entry

#### Expanded Ford GT visual-state matrix

The initial Ford GT paint-type trio was useful because it proved that the active signal sits at
byte `+4`, not byte `+0`. A broader controlled set was then checked using the same career
`Ford GT` (`parts_slot 46`):

- `fixture-a(stock Ford_GT(gloss_A))`
- `fixture-a(Ford_GT_gloss_color_B)`
- `fixture-a(Ford_GT_metallic_color_A)`
- `fixture-a(Ford_GT_mettalic_color_B)`
- `fixture-a(Ford_GT_custom_color_A)`
- `fixture-a(Ford_GT_custom_color_B)`
- `fixture-a(Ford_GT_only_changed_body_vinyl)`
- `fixture-a(Ford_GT_only_changed_window_tint)`

Block-level findings versus the gloss-A baseline:

- `gloss_B`: only `+0x098` (`Paint`) changed, from `0x2E` to `0x34`
- `metallic_A`: only `+0x098` changed, from `0x2E` to `0x7E`
- `metallic_B`: only `+0x098` changed, from `0x2E` to `0x83`
- `custom_A`: only `+0x098` changed, from `0x2E` to `0xCE`
- `custom_B`: only `+0x098` changed, from `0x2E` to `0xD3`
- `body_vinyl`: only `+0x09A..+0x09B` changed, from `FFFF` to `0D12`
- `window_tint`: only `+0x106` changed, from `0x23` to `0x24`

At the same time, the `0x5577` table showed:

- byte `+0` of each entry stayed unchanged across this whole set
- byte `+4` changed across the repeated regular rows
- the final entry (`index 56`) has a different structure and behaves like a special tail /
  footer record rather than another regular mode row
- the first `56` regular rows changed together, while the tail stayed `0x00`

Observed `0x5577+4` regular-row values from this set:

- `gloss_A` (`Paint = 0x2E`) -> `0x01`
- `gloss_B` (`Paint = 0x34`) -> `0x03`
- `metallic_A` (`Paint = 0x7E`) -> `0x00`
- `metallic_B` (`Paint = 0x83`) -> `0x02`
- `custom_A` (`Paint = 0xCE`) -> `0x02`
- `custom_B` (`Paint = 0xD3`) -> `0x00`
- `body_vinyl` only -> `0x00`
- `window_tint` only -> `0x03`

Current interpretation:

- byte `+4` is still the leading active subfield; current evidence does **not** support byte
  `+0` as the operative visual-mode signal
- the earlier over-simple mapping `Gloss/Metallic/Custom -> 0x01/0x00/0x02` is **not**
  sufficient
- `0x5577+4` is a broader global visual mode/state byte:
  - color changes within the same paint family can move it
  - non-paint edits such as body vinyl and window tint can move it
- the table is still not proven to be fully car-local replay data; it may remain
  global/frontend state that influences how the current visual mode is interpreted

Current policy:

- snapshot extraction reports both:
  - legacy byte `+0`
  - primary mode byte `+4`
- injector work must not replay this state yet
- future injector work may target only the uniform `0x5577+4` mode value if later
  testing proves that this is sufficient for visual fidelity

#### Ford GT -> Fiat active-car swap test

Two additional saves were compared:

- `fixture-a(switched_to_Ford_GT)`
- `fixture-a(switched_to_Fiat)`

The intent of this test was to see whether merely changing the active car in the garage would
reset or rewrite `0x5577` if the table were just an "active car render cache".

Observed result:

- `0x5577` had **zero diffs** between the two saves
- byte `+0` stayed unchanged
- byte `+4` stayed unchanged
- the special tail entry also stayed unchanged

At the same time, the save did record the active-car switch elsewhere:

- absolute offset `0x4034` changed from `95` to `104`
- these values match the career `car_number` values of:
  - `Ford GT` -> `95`
  - `Fiat Punto` -> `104`
- the remaining diffs were integrity/header-tail bytes (`CRC` / `MD5`) rather than new visual
  payload

Implication:

- the simple hypothesis "`0x5577` is only a transient cache for whichever car is currently
  active" is **not** supported by this test
- active-car selection can change while `0x5577` remains bit-identical
- `0x5577+4` still looks like a broader global visual/render state, but not a field that simply
  tracks the currently selected car

#### Active career car pointer (`0x4034`)

Three additional controlled saves were then compared from `GaySIgm`:

- `Active_Normal_A(active car is cobalt_ss)`
- `Active_Normal_B(active car is supra(should be pink slip))`
- `Active_Normal_C(active car is a stock audiTT)`

Observed result:

- the only diff in the local window `0x4020..0x4050` between each pair was byte `0x4034`
- `0x4034` matched the selected career-linked car's `car_number` in all three cases:
  - `Chevrolet Cobalt SS` (`Career`, slot `0`) -> `car_number 81`
  - `Toyota Supra` (`Pink Slip`, slot `3`) -> `car_number 84`
  - `Audi TT Quattro` (`Career`, slot `1`) -> `car_number 85`
- this confirms that the field tracks the active career vehicle by **car number**, not by
  `career_slot`
- `Pink Slip` cars participate in the same mechanism; there is no separate active-pointer format
  for them

Broken-state correlation on `fixture-e`:

- in healthy saves where `Ford Mustang GT?` was still career-linked, `0x4034 = 81` matched that
  same car in `Career`
- in `fixture-e.bak_20260328_140200.bak_20260328_155920`, only one career car remained
  (`BMW M3 GTR`, pink-slip slot `25`), but `0x4034` still stayed `81`
- in both broken saves:
  - `fixture-e(broken save nr2)`
  - `fixture-e(broken save, 0 career cars)`
  `0x4034` still stayed `81`
- in those broken saves, `81` resolved to `Ford Mustang GT?` in `My Cars`, not to any
  career-linked vehicle

Implication:

- `0x4034` is now strongly confirmed as the save-level active career-car pointer
- the field stores the active vehicle's **career car_number**
- the broken `Career garage` state correlates with leaving `0x4034` pointing at a car that no
  longer exists among career-linked owned records
- future safety/product work should no longer be framed as only "keep at least one car in
  Career"; it must preserve or retarget `0x4034` to a surviving career-linked car

#### Profile alias / displayed name (`0x5A31`)

The displayed profile name is not currently parsed by the editor, but a stable field was
isolated by checking multiple independent saves:

- `fixture-a`
- `fixture-e`
- `Bkmz-1`
- `GaySIgm`
- `John`
- `fixture-f`
- `fixture-c`
- `fixture-i`
- `fixture-b`
- `fixture-d`
- `AllCars`

Observed result:

- each healthy save contains one stable match for the displayed alias at absolute offset
  `0x5A31`
- the same field is still authoritative even when the file name is not; for example,
  `SAVE_B_tokens\\SAVE_B_tokens` still stores `fixture-a` at `0x5A31`
- relative to saved data start (`0x34`), this is `saved_data + 0x59FD`

Observed layout around the field:

- `0x5A2D..0x5A30` -> unknown `u32`-like field, not part of the alias text
- `0x5A31..0x5A54` -> alias buffer
- `0x5A55..0x5A60` -> next stable structure:
  - `03 CD CD CD 01 00 00 00 01 CD CD CD`

Observed encoding:

- single-byte null-terminated text
- all tested saves decode cleanly as plain ASCII
- no tested save showed a UTF-16LE copy of the alias

Observed storage behavior:

- the alias string starts exactly at `0x5A31`
- it is followed by `0x00`
- the remainder of the buffer is zero-padded up to `0x5A54`
- the next non-zero byte is always at `0x5A55`

Practical length conclusion:

- the alias buffer size is `0x24` bytes (`36` bytes)
- the safe maximum stored text length is therefore `35` bytes if the game expects a trailing
  null terminator
- the longest observed alias in the current test set is `fixture-d` (`8` bytes)

What is still not claimed:

- the exact in-game UI input limit for creating/editing a profile name
- whether non-ASCII code pages are accepted in-game, even though the save field is clearly
  single-byte and ASCII-compatible in all tested files

#### End-to-end injector fidelity test (`My Cars`, primary-only donor)

An end-to-end injector test was then run with:

- donor: `fixture-a` -> `My Cars Ford GT` (`primary-only`, `requires_unresolved_global_visual_state = true`)
- clean target: `fixture-c`
- injection mode: `My Cars`

Pre-game injected state:

- the injected `Ford GT` had the donor `0x198` build copied correctly:
  - `Paint = 54`
  - `Body Vinyl = CF 11`
  - `Window Tint = 23`
- no sidecar was present
- `0x5577+4` in the clean target stayed at the target-native value `0x00`, not the donor's
  `0x03`
- `0x5577+0` also started at `0x00`

After first in-game render and save (`fixture-c(TARGET_after_first_render_save)`):

- in-game appearance was visually correct in `My Cars`
- the injected `Ford GT` primary block had **zero diffs**
- sidecar presence still stayed `false`
- `0x5577+4` still stayed `0x00`
- `0x5577+0` changed uniformly across all `57` table rows from `0x00` to `0x03`

Implication:

- for this primary-only donor, injector fidelity did **not** require replaying the donor's
  `0x5577+4` value
- the game rendered the car correctly from the copied primary build data alone
- the save written after first render did mutate `0x5577`, but it mutated byte `+0`, not byte
  `+4`
- current strongest product conclusion:
  - `Injector v1` can keep ignoring `0x5577` for primary-only snapshot injection
  - any future `0x5577` work is now about understanding post-render global state, not about
    unblocking current primary-only injector fidelity

## Resulting implementation model

The editor now treats Profile data as two joined layers:

1. `PursuitRecord`
   - bounty
   - escaped
   - busted
   - source block: `0xE2ED`

2. `CareerVehicleRecord`
   - car number
   - signature
   - flags
   - parts slot
   - career slot
   - source block: `0x6219`

3. `ResolvedGarageEntry`
   - built by joining both layers through `career_slot`
   - used by the Profile UI

Write policy:
- bounty edits write only into the pursuit block
- car identity data is read-only in the current implementation
- parts editing writes only to the confirmed per-car parts block fields:
  - regular levels at `+0x118 .. +0x130`
  - Junkman mask at `+0x134`
- writes must validate the parts-block marker `<parts_slot> CD CD CD` before touching data
- `Junkman Turbo` requires regular `Turbo > 0`
- `Junkman NOS` requires regular `NOS > 0`
- regular performance levels are clamped by the confirmed model caps from `core/tuning_limits.py`

## Known limitations

Still not fully resolved:
- exact meaning of flags at `+0x0C`
- exact meaning of field at `+0x0E`
- the meaning of the rest of the per-car parts block outside `+0x118..+0x137`
- the surrounding structure around `0x4034`; only the active-car byte itself is currently
  confirmed

Current fallback policy:
- if a future save has no unique car-record match for a pursuit slot, the UI should
  show an honest fallback instead of guessing a vehicle name

## Pursuit heat RE (`fixture-g`, 2026-04-09)

Controlled saves on the same `Audi TT Quattro` career car:
- `fixture-g(BASE)`
- `fixture-g(heat level 2 and a bit)`
- `fixture-g(heat level 3)`

Confirmed pursuit record:
- block base: `0xE2ED`
- stride: `0x38`
- tested record: `career_slot 1`, absolute offset `0xE325`

Confirmed heat fields inside one pursuit record:
- `+0x0C .. +0x0F` = primary heat meter as `float32`
- `+0x06 .. +0x07` = zero-based integer heat tier mirror
- repeated integer mirrors also move with heat at:
  - `+0x1E`
  - `+0x20`
  - `+0x22`
  - `+0x24`
  - `+0x26`

Observed values:
- base save:
  - `+0x0C = 1.0`
  - `+0x06 = 0`
- heat level 2 with partial progress:
  - `+0x0C = 2.1613526344`
  - `+0x06 = 1`
- heat level 3:
  - `+0x0C = 3.0`
  - `+0x06 = 2`

Interpretation:
- the game persists the visible heat state as a full `float32`, not only as an integer level
- UI heat `xN` appears to correspond to `floor(heat_float)`
- the integer mirrors are stored zero-based:
  - visible `x1` -> stored `0`
  - visible `x2` -> stored `1`
  - visible `x3` -> stored `2`

Backend product rule adopted in the editor:
- read path now exposes:
  - `heat`
  - `heat_level`
- write path updates both:
  - primary heat float at `+0x0C`
  - all confirmed zero-based mirror fields
- pursuit-slot reset / initialization now restores heat baseline `1.0`
- current safe write range is `1.0 .. 5.0` (Most Wanted heat scale assumption)

## Practical validation summary

Validated against real saves:
- `fixture-a`
- `fixture-b`
- `fixture-c`
- `fixture-d`

Confirmed in code:
- Profile vehicle labels can be resolved from signatures
- pursuit totals remain correct
- bounty editing still targets the pursuit block only
- filler records in the car block are ignored
- Parts Viewer v2 can decode confirmed performance levels and Junkman categories
- Parts Editor v1 can stage and write only the confirmed parts fields, with Turbo/NOS Junkman prerequisites enforced
