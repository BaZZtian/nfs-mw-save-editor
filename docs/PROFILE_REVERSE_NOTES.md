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
- `+0x04 .. +0x07` = zero-based integer heat tier mirror packed into the high `u16` of a `u32`
- `+0x06 .. +0x07` = zero-based integer heat tier mirror
- `+0x1C .. +0x1F` = zero-based integer heat tier mirror packed into the high `u16` of a `u32`
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
  - all confirmed zero-based mirror fields, including the `u32` high-half mirrors at `+0x04` and `+0x1C`
- pursuit-slot reset / initialization now restores heat baseline `1.0`
- current safe write range is `1.0 .. 5.0` (Most Wanted heat scale assumption)

Follow-up after first editable heat UI pass:
- the initial editor implementation only updated `+0x06` and `+0x1E/+0x20/+0x22/+0x24/+0x26`
- it did **not** update the additional `u32` mirrors at `+0x04` and `+0x1C`
- this matched the observed bug pattern:
  - garage/editor-facing heat changed
  - in-game pursuit behavior could still follow the old level
- backend was then corrected to write the full confirmed mirror set
- if gameplay still diverges after this fix, the next RE target is a second gameplay-facing heat companion outside the local pursuit record

#### Pursuit-record signature variants (`fixture-i`, `fixture-e`)

Later validation on longer/anomalous saves showed that the pursuit block is not limited to only one
record signature variant.

Observed valid per-slot signatures at bytes `+0x01..+0x03`:

- normal slots: `CD 03 00`
- later valid slots also appear as:
  - `CD 04 00`
  - `CD 05 00`

Examples:

- `fixture-i(base_heat_level5)`:
  - slot `10` (`0xE51D`) uses `CD 04 00`
  - slots `11..23` continue as valid pursuit records after it
- `fixture-e`:
  - slot `24` (`0xE82D`) uses `CD 05 00`

Practical implication:

- the editor's original pursuit parser stopped at the first non-`CD 03 00` record
- this truncated the tail of the pursuit block on saves like `fixture-i` and `fixture-e`
- later career cars then falsely appeared as having:
  - no pursuit link
  - no editable heat
  - no linked bounty/escaped/busted data

Current parser policy:

- treat all three variants as valid pursuit-record signatures:
  - `CD 03 00`
  - `CD 04 00`
  - `CD 05 00`
- keep `00 00 CD CD` at `+0x08..+0x0B` as the second required signature half

What this does **not** prove yet:

- the semantic meaning of `03` vs `04` vs `05`
- whether those values encode a subtype, state, or simply another accepted record form

#### Visual-only heat decay saves (`fixture-i`)

New controlled saves on the same active `Mazda RX-8` career car:

- `fixture-i(base_heat_level5)`
- `fixture-i(heat_level4_changed_only_rims_color)`
- `fixture-i(heat_level3_changed_only_paint_color)`
- `fixture-i(heat_level2_changed_only_paint_color_back)`
- `fixture-i(heat_level1_changed_only_paint_color_again)`

Method:

- start from a real `heat x5` save
- lower heat only through visual changes in-game
- no new pursuit was run between the comparison points

Observed result on the active car's local pursuit record (slot `20`, `0xE74D`):

- the primary heat float at `+0x0C` changed cleanly:
  - `5.0`
  - `4.850000381`
  - `3.395000219`
  - `2.376500130`
  - `1.663550019`
- the previously identified integer mirror set did **not** track these visual-only changes in the
  same way:
  - several mirrors stayed stale or static
  - this strongly suggests the float is the real persisted heat meter, while at least some integer
    fields behave more like caches or sub-state mirrors than the primary source of truth

Additional duplicate-heat clue:

- the exact same changing float sequence also appeared at absolute offset `0x498`
- this points to a second heat-related companion/cache field outside the local pursuit record
- this companion is still not mapped well enough to write safely

Current interpretation:

- per-car heat is definitely persisted in the local pursuit record as a `float32`
- garage/display heat follows that local value
- gameplay may still involve an additional companion/cache field outside the pursuit block, and
  that second field remains unresolved

#### End-to-end editor validation on `fixture-i`

After fixing the pursuit parser to accept `CD 04 00` / `CD 05 00` variants, a live in-game smoke was
run on the `fixture-i` save:

- source: `fixture-i(base_heat_level5)`
- editor action: set the active `Mazda RX-8` heat from `x5` down to `x1`

Observed result:

- garage UI in-game showed `x1`
- HUD during free-roam / pursuit also showed `x1`
- the first spawned cop matched heat `x1`
- later cop spawns also stayed at heat `x1`

Implication:

- the current backend heat write path is now sufficient on at least one clean/normal save
- local pursuit-record heat editing is no longer just a garage-only/display-only change
- the remaining problematic saves (`fixture-g`, some `fixture-e` cases) should now be treated as anomaly /
  special-context cases rather than proof that the global heat model is still fundamentally wrong

## Career progression / heat-cap RE (`KSWD`, 2026-04-10)

New progression-pair save set:

- `KSWD(Before_beating_Vic)` / `KSWD(After_beating_Vic)`
- `KSWD(Before_beating_Earl)` / `KSWD(After_beating_Earl)`
- `KSWD(Before_beating_Webster)` / `KSWD(After_beating_Webster)`

These pairs are not perfectly clean; they contain substantial progression/stat noise beyond a single
flag change. However, one very strong common progression marker was isolated:

- absolute offset `0x4C` as `u32`
- observed values:
  - before Vic: `5`
  - after Vic: `6`
  - before Earl: `9`
  - after Earl: `10`
  - before Webster: `13`
  - after Webster: `14`

This fits the simple blacklist progression model:

- `field_0x4C = 19 - current_blacklist_rank`

Examples:

- rank `#14` -> `5`
- rank `#13` -> `6`
- rank `#10` -> `9`
- rank `#9` -> `10`
- rank `#6` -> `13`
- rank `#5` -> `14`

Cross-check on other saves:

- earlier/mid-game style saves:
  - `fixture-g` -> `0x4C = 7`
  - `GaySIgm` -> `0x4C = 7`
  - `fixture-c` -> `0x4C = 7`
- late-game style saves:
  - `fixture-i` -> `0x4C = 17`
  - `fixture-a` -> `0x4C = 17`
  - `fixture-e` -> `0x4C = 17`
  - `fixture-f` -> `0x4C = 17`

Practical interpretation:

- `0x4C` is now a strong save-level candidate for current blacklist progression / player-rank-like
  state
- this progression almost certainly participates in global unlock logic, including police heat caps

Important negative result:

- changing **only** `0x4C` on `fixture-g` (`7 -> 10 -> 14 -> 17`) did **not** unlock correct gameplay
  heat behavior
- pursuit still behaved like the original capped save, despite the patched progression value

Implication:

- `0x4C` is useful and likely real, but it is **not sufficient by itself**
- heat-cap progression is therefore controlled by:
  - either multiple save fields
  - or `0x4C` plus one or more companion unlock flags/state blocks
- future RE should treat progression as a multi-field model rather than a single-rank scalar

## Save-hopping progression bug candidate (`KSWD(Base)` -> bugged `KSWD`, 2026-04-10)

New comparison target:

- clean baseline: `KSWD(Base)` (byte-identical to `KSWD(Before_beating_Earl)`)
- bugged save: `KSWD`

Observed in-game:

- loading a later-progression save first, then loading `KSWD`, can mark Earl as already defeated and
  expose upgrades that should still be locked

Binary diff result:

- total payload diff is tiny: only `26` bytes differ
- meaningful non-checksum diff is isolated to:
  - `0x4040..0x4041`
- exact change:
  - baseline: `03 08` (`u16 = 0x0803 = 2051`)
  - bugged: `F7 1D` (`u16 = 0x1DF7 = 7671`)
- all other semantic profile markers checked so far stayed the same:
  - `0x4C = 9`
  - money unchanged
  - active car unchanged
  - career vehicle table unchanged
  - pursuit record count unchanged

Cross-check against clean blacklist progression pairs:

- `Before/After Vic`, `Before/After Earl`, `Before/After Webster` all keep:
  - `0x4040 = 0x0803`
- therefore `0x4040` is **not** the same field as the clean blacklist-rank marker `0x4C`

Practical interpretation:

- `0x4040..0x4041` is now a strong candidate for a small profile-wide unlock / defeated-state
  bitfield or sticky cache block
- the save-hopping bug appears to overwrite this small state while leaving normal rank/progression
  fields intact
- the exact bugged value `0x1DF7` also appears on several later / modified saves, including
  `fixture-f`, which matches the reproduced load order that triggered the bug

Current working model:

- `0x4C` = broad blacklist progression / current-rank style field
- `0x4040` = separate companion unlock-state / sticky state candidate
- future progression-cap RE should treat both as part of a multi-field model

## `fixture-g` free-roam vs active-pursuit heat mismatch (2026-04-10)

Additional in-game observation on `fixture-g`:

- outside active pursuit, in free roam, the minimap/HUD can still show the edited local car heat
  correctly (example observed: `x4` after passive decay from edited `x5`)
- the moment a cop detects the player and active pursuit starts, the visible heat immediately clamps
  down to `x3`

Practical interpretation:

- free-roam display can still reflect the per-car pursuit heat stored in the save
- active pursuit startup applies a second gameplay-facing cap / unlock rule
- this strongly supports the two-layer model:
  - local per-car heat in the pursuit record
  - separate global progression / unlock-state gate applied when pursuit actually begins

Important follow-up:

- `fixture-g` already carries the late-style `0x4040 = 0x1DF7`, the same value seen on `fixture-i`,
  `fixture-f`, and the bugged `KSWD`
- therefore `0x4040` alone is **not** sufficient to explain the pursuit-time clamp
- next test pack should patch combinations of:
  - `0x4C`
  - nearby small profile bytes around `0x4038` / `0x403D..0x4041`
  - known working late-game donor values

## `fixture-g` progression gate test pack results (2026-04-10)

Test pack used:

- `fixture-g_test_00_baseline`
- `fixture-g_test_01_rank_only_0x4C_17`
- `fixture-g_test_02_fixture-i_profile_block_only`
- `fixture-g_test_03_rank_17_plus_fixture-i_profile_block`
- `fixture-g_test_04_webster_threshold_block`

In-game validation results:

- `00` baseline:
  - no change
- `01` (`0x4C` only):
  - no visible change
  - therefore `0x4C` alone does not drive cars / cops / unlock behavior
- `02` (fixture-i-style small profile block only):
  - game behaves like post-Razor / endgame
  - cars are fully unlocked
  - cops keep `x5` correctly in active pursuit
- `03` (`0x4C = 17` plus same small fixture-i block):
  - same result as `02`
  - extra confirmation that `0x4C` is not the authoritative gate here
- `04` (Webster-threshold style block):
  - game behaves like current blacklist target is `JV` (`#4`)
  - boss is **not** incorrectly crossed out
  - dealership cars unlock correctly for that later story point
  - cops keep `x5` correctly in active pursuit
  - performance upgrades remain on the old lower-story unlock state (example observed: still gated at
    blacklist `#11`)

Practical interpretation:

- the byte immediately before money, `0x4038`, is now the strongest save-level candidate for
  `player rank` / current blacklist target
  - this matches old CE lore that rank was a `1 byte` field directly before money
  - changing it from `0x0B` to `0x04` on `fixture-g` produces a game state that behaves like blacklist
    `#4` (`JV`)
- `0x4C` remains useful as a progression marker, but is not authoritative for:
  - police heat cap
  - dealership car unlocks
- `0x4040..0x4041` still looks like a separate defeated-state / sticky unlock-state candidate
  - it explains the `KSWD` load-hopping bug
  - but it is not sufficient by itself for the `fixture-g` pursuit clamp

New working model:

- `0x4038` = likely `player rank` / current blacklist member
- `0x4040..0x4041` = companion defeated-state / sticky progression cache
- `0x4C` = broader progression counter / derived story marker
- performance-parts unlocks are controlled by at least one additional field outside this small profile
  block

Current product implication:

- police heat cap and dealership car unlocks now look much more likely to follow `0x4038`-style
  progression than `0x4C`
- parts/performance unlock editing should be treated as a separate RE target

## `KSWD_only_0x4040_patched_from_base` gameplay confirmation (2026-04-10)

Controlled file:

- `KSWD_only_0x4040_patched_from_base`
- this file was produced from clean `KSWD(Base)` by changing **only** `0x4040..0x4041`
  from `0x0803` to `0x1DF7`, then recomputing integrity
- it is byte-identical to the naturally bugged `KSWD`

In-game validation result:

- Earl is shown as already defeated / crossed out
- story progression becomes a dead-end:
  - current boss still appears to be Earl
  - Earl cannot actually be raced again
  - the next blacklist slot does not advance normally
- performance parts unlock all the way up to late-game / near-endgame tiers
- dealership cars remain on the older Earl-era story gate
  - cars still look like the game believes progression is around Earl / blacklist `#9`

Practical interpretation:

- `0x4040..0x4041` is now strongly confirmed as a **separate sticky unlock-state / defeated-state**
  block
- changing only this block is sufficient to:
  - mark a boss as already defeated
  - over-unlock performance parts
  - create a softlocked / contradictory story state
- but it is **not** sufficient to move dealership car progression forward

This gives a cleaner progression split:

- `0x4038` = likely current blacklist target / player rank
- `0x4040..0x4041` = defeated-state / sticky unlock cache with strong impact on parts unlocks
- dealership car availability follows a different progression layer than the late-game parts unlocks

## `KSWD` rank-byte-only test pack results (`0x4038`, 2026-04-11)

Controlled pack:

- `KSWD_rankbyte_09_baseline`
- `KSWD_rankbyte_0B_biglou_only`
- `KSWD_rankbyte_04_jv_only`
- `KSWD_rankbyte_01_razor_only`

All files were produced from clean `KSWD(Base)` by changing **only** `0x4038`, keeping:

- `0x4040 = 0x0803`
- `0x4C = 9`

In-game validation results:

- baseline `0x4038 = 9`:
  - normal Earl `#9` state
  - cars, parts, and cops all behave as expected for that progression point
- `0x4038 = 11` (`Big Lou`):
  - current boss changes to `Big Lou #11`
  - boss requirements appear fulfilled but `Challenge Rival` button is missing
  - dealership cars are limited to the `#11` story point
  - parts remain on the original Earl-era state
  - current owned car can appear self-locked in garage rotation
  - cops remain baseline (`x3`), which is still correct for that story point
- `0x4038 = 4` (`JV`):
  - game behaves like Webster `#5` was just beaten
  - post-Webster phone call triggers
  - dealership cars unlock correctly up to the `#4` story point
  - cops / heat progression move beyond the old `x3` cap and behave as if higher heat is unlocked
  - parts stay on the older Earl-era state (`#9`)
- `0x4038 = 1` (`Razor`):
  - game behaves like Bull `#2` was just beaten
  - all dealership cars are available
  - cops / heat progression behave like late-game / `x5`-cap state
  - parts still remain on the older Earl-era state (`#9`)

Side observation:

- on the forward-patched story states (`JV`, `Razor`), milestone icons stay visually padlocked in the
  blacklist screen, but the game still appears willing to let the player attempt them

Practical interpretation:

- `0x4038` is now strongly supported as the save-level field for:
  - current blacklist target / player rank
  - dealership car availability
  - police heat-cap progression
- `0x4038` alone does **not** control:
  - performance-parts unlocks
  - some readiness / UI availability logic such as the missing `Challenge Rival` button
  - milestone lock icon presentation

Updated progression split:

- `0x4038` = current boss / player-rank-like story pointer
- `0x4040..0x4041` = defeated-state / sticky unlock cache with strong influence on parts unlocks
- at least one additional field still controls:
  - rival-challenge readiness
  - milestone icon-lock state
  - or other blacklist screen gating details

## New performance candidate block (`0x42F0..0x4C5F`, 2026-04-11)

Current best candidate for the **normal** performance-upgrade unlock tables is the dense table-like region
`0x42F0..0x4C5F`.

Why this range is now the leading candidate:

- `0x4038`-only rank tests do **not** change it, even though:
  - current boss changes
  - dealership cars change
  - cop heat-cap progression changes
- `0x4040`-only bug reproduction also leaves it untouched, even though the sticky cache can still over-unlock parts
- clean `KSWD(After_beating_Earl)` changes only a sparse subset of this range
- clean `KSWD(After_beating_Webster)` populates a much larger subset of the same range

This makes the range a much better candidate for **normal performance progression** than:

- `0x55D0..0x55E7`, which user testing already showed belongs to the visual/body-parts unlock family
- `0x0C80..0x0CA0` / `0x0C8C..0x0C8E`, which currently look more like volatile event / queue / session state than clean unlock tables

Working model:

- `0x42F0..0x4C5F` = normal performance-unlock tables or a closely related family of upgrade gates
- `0x4040..0x4041` = separate defeated-state / sticky override that can over-unlock performance without touching the normal tables

Prepared test pack:

- `local test pack: kswd_performance_unlock_test`

Variants:

- `KSWD_perf_00_baseline`
- `KSWD_perf_01_after_earl_sparse_region`
- `KSWD_perf_02_after_webster_sparse_region`
- `KSWD_perf_03_after_webster_frontblock_42F0_48BF`
- `KSWD_perf_04_after_webster_tailblock_4B40_4C5F`

## `0x42F0..0x4C5F` failed as performance candidate; new family at `0xA7F0..0xAC5F` (2026-04-12)

User testing of the first performance-unlock pack showed:

- performance upgrades stayed baseline in every variant
- dealership cars stayed baseline
- police heat / cops stayed baseline
- only the front half of the range (`0x42F0..0x48BF`) caused a side effect:
  - current boss stayed `Earl`
  - `Challenge Rival` button disappeared
  - story became softlocked

Practical interpretation:

- `0x42F0..0x4C5F` is **not** the normal performance-upgrade gate
- `0x42F0..0x48BF` is more likely blacklist / rival-readiness / challenge-availability state
- `0x4B40..0x4C5F` showed no useful visible effect in isolation

Follow-up candidate search isolated a new late-game-populated family around:

- `0xA7F0..0xA92F`
- `0xAA90..0xAACF`
- `0xAB20..0xAC5F`

Why this family is stronger:

- clean `KSWD(Base)` / `KSWD(Before_beating_Earl)` keep this area mostly empty / sparse
- clean `KSWD(After_beating_Webster)` populates it heavily with structured values
- `fixture-i` also carries a populated late-game version of the same family
- `fixture-g` carries an earlier / smaller-state version

Working model:

- `0x5580..0x561F` family = normal visual/body-parts unlock tables
- `0x42F0..0x48BF` = blacklist challenge-readiness / UI gating companion state
- `0xA7F0..0xAC5F` = new leading candidate family for normal performance-upgrade unlocks

Prepared second test pack:

- `local test pack: kswd_performance_unlock_test_v2`

Variants:

- `KSWD_perf2_00_baseline`
- `KSWD_perf2_01_after_webster_A7F0_A92F`
- `KSWD_perf2_02_after_webster_AA90_AACF`
- `KSWD_perf2_03_after_webster_AB20_AC5F`
- `KSWD_perf2_04_after_webster_full_A7F0_AC5F`
- `KSWD_perf2_05_fixture-i_full_A7F0_AC5F`

## `0xA7F0..0xAC5F` also failed; compact candidate at `0xA775..0xA790` (2026-04-12)

User testing of `kswd_performance_unlock_test_v2` showed:

- baseline remained baseline
- all patched variants still kept:
  - current boss = `Earl`
  - dealership cars = baseline
  - cops / heat = baseline
  - performance upgrades = baseline
  - visual/body parts = baseline
  - paint = baseline

So the populated late-game family at `0xA7F0..0xAC5F` is **not** the normal performance-upgrade gate.

Follow-up scan on clean `KSWD` progression saves exposed a much smaller progression-like table
immediately before that failed family:

- `0xA775`
- `0xA779`
- `0xA77D`
- `0xA781`
- `0xA785`
- `0xA78D`

This behaves like six small zero-based counters:

- `Before/After Vic`: `[0, 0, 0, 0, 0, 0]` with the last value also `0`
- `Before/After Earl`: `[1, 1, 1, 1, 1, 2]`
- `Before/After Webster`: `[2, 2, 2, 2, 2, 3]`

That shape is much more plausible for a compact upgrade-tier table than the previously tested large blocks.

Prepared third test pack:

- `local test pack: kswd_performance_unlock_test_v3`

Variants:

- `KSWD_perf3_00_baseline`
- `KSWD_perf3_01_after_webster_values_A775_A78F`
- `KSWD_perf3_02_after_webster_full_A760_A79F`
- `KSWD_perf3_03_fixture-i_values_A775_A78F`
- `KSWD_perf3_04_fixture-i_full_A760_A79F`

## `0xA775..0xA790` is installed-parts data, not unlock state (2026-04-12)

In-game validation exposed the actual behavior of `kswd_performance_unlock_test_v3`:

- parts remained padlocked by story progression
- but the currently viewed / installed performance packages on the car changed

That matches the save layout exactly:

- `PARTS_BLOCK_BASE_OFFSET = 0x9CCD`
- `PARTS_BLOCK_SIZE = 0x198`
- `PARTS_LEVELS_BASE_OFFSET = 0x118`
- `0xA775 = 0x9CCD + 6 * 0x198 + 0x118`

So `0xA775` lands exactly at the **levels table** of parts slot `37`:

- slot index `37`
- inside the confirmed installed performance-level payload, not in global unlock state

Practical interpretation:

- the `0xA775..0xA790` six-counter pattern is real, but it is per-car installed parts data
- it is not the performance-upgrade unlock gate
- `kswd_performance_unlock_test_v3` should be treated as a false lead and does not need further gameplay testing

## Global keyed record-table candidate for normal parts/performance unlocks (2026-04-12)

After excluding per-car parts regions and the failed profile-block candidates, a stronger
global progression table was isolated in the early profile area.

### Shape

- save-specific starts observed via stable 8-byte key `BC 64 0A 85 D9 1D C7 78`
  - `KSWD(Before_beating_Vic)`: `0x0494`
  - `KSWD(After_beating_Vic)`: `0x0484`
  - `KSWD(Before_beating_Earl)`: `0x04B4`
  - `KSWD(After_beating_Earl)`: `0x04C4`
  - `KSWD(Before_beating_Webster)`: `0x04F4`
  - `KSWD(After_beating_Webster)`: `0x0504`
  - `fixture-g`: `0x0494`
  - `fixture-i(base_heat_level5)`: `0x04C4`
- record stride: `0x14`
- stable logical record count before structure break: `55`
- record layout:
  - `key[0:8]`
  - `fld[8:12]`
  - `tail[12:20]`

### Why this is stronger

- untouched by:
  - `0x4038`-only rank-byte tests
  - `0x4040..0x4041` defeated-state/cache corruption
- therefore it is separate from:
  - current boss / dealership cars / cops heat cap
  - sticky defeated-state / broken late-game override
- progression changes appear in `fld[0]` with a clean three-state pattern:
  - `1` = future / locked
  - `2` = current tier
  - `4` = past / completed tier

### Clean KSWD ladder pattern

- `Before_beating_Vic` baseline:
  - groups `1..15` mostly stay at `fld[0] = 1`
- `After_beating_Vic`:
  - indices `43..45` (`group 12`) become `2`
- `Before_beating_Earl`:
  - indices `32..45` (`groups 9..12`) become `4`
- `After_beating_Earl`:
  - indices `28..31` (`group 8`) become `2`
- `Before_beating_Webster`:
  - indices `16..31` (`groups 5..8`) become `4`
- `After_beating_Webster`:
  - indices `12..15` (`group 4`) become `2`
- `fixture-i(base_heat_level5)`:
  - indices `0..54` effectively carry the fully late-game `4` state

This is the cleanest global progression registry found so far that is still independent
from `0x4038` and `0x4040`.

### New proof-test pack

Prepared from clean `KSWD(Base)` by patching only `fld[0]` of this keyed table:

- `local test pack: kswd_unlocktable_test`
  - `KSWD_unlocktable_00_baseline`
  - `KSWD_unlocktable_01_after_earl_grp8_current`
    - patched indices: `28..31`
  - `KSWD_unlocktable_02_before_web_grp5_8_past`
    - patched indices: `16..31`
  - `KSWD_unlocktable_03_after_web_grp4_current_grp5_8_past`
    - patched indices: `12..31`
  - `KSWD_unlocktable_04_fixture-i_all_groups_late`
    - patched indices: `0..31`

All variants were saved through `SaveFile.save(...)` and validated `MD5/CRC1/CRC2 OK`.

Current goal:

- determine whether this table drives the normal parts/performance unlock layer while
  leaving:
  - boss/story state
  - dealership cars
  - cops/heat
  untouched at baseline

## `kswd_unlocktable_test` outcome: blacklist summary / career-progress layer, not parts/performance (2026-04-12)

In-game validation results for:

- `KSWD_unlocktable_01_after_earl_grp8_current`
- `KSWD_unlocktable_02_before_web_grp5_8_past`
- `KSWD_unlocktable_03_after_web_grp4_current_grp5_8_past`
- `KSWD_unlocktable_04_fixture-i_all_groups_late`

Observed behavior:

- current boss still shows correctly as `Earl`
- `Challenge Rival` button remains available
- dealership cars stay baseline
- cops / heat stay baseline
- visual/body parts stay baseline
- performance upgrades stay baseline
- but earlier blacklist rivals show broken summary counters:
  - `Race Wins = 0`
  - `Milestones Completed = 0`
  - bounty remains intact because it is global
- race-event grids still show completed races
- milestone icons show padlocks even though milestones remain playable
- overall career completion percentage drops (`36% -> 26%` observed)

Practical interpretation:

- the keyed early-profile record table is **not** the normal parts/performance unlock gate
- it is a separate blacklist summary / milestone-count / career-progress presentation layer
- it likely feeds:
  - rival summary counters on blacklist cards
  - milestone lock presentation
  - aggregate career completion percentage
- it does **not** appear to be the authoritative source for:
  - race completion flags
  - dealership cars
  - cops/heat progression
  - performance shop unlocks

## New compact profile-entry candidate for late unlocks at `0x412C..0x4260` (2026-04-12)

After excluding the keyed summary table, a separate family of fixed 4-byte entries in the
profile block remains a strong candidate for normal shop unlocks.

### Structure

Within `0x4060..0x4270`, data is laid out as 4-byte entries that look like:

- `[state_word_lo, state_word_hi, 0x00, entry_id]`

Observed examples in clean `KSWD(Base)`:

- `0x412C`: `00 00 00 3B`
- `0x4130`: `00 00 00 3C`
- `0x4258`: `00 00 00 86`

Observed examples in clean `KSWD(Before_beating_Webster)`:

- `0x412C`: `04 29 00 3B`
- `0x4130`: `04 2A 00 3C`
- `0x4258`: `04 32 00 86`

So this family behaves like fixed entry IDs whose state words transition from `0x0000`
to non-zero `0x??04` values as progression advances.

### Clean ladder behavior

Compared with `KSWD(Base)` / `KSWD(Before_beating_Earl)`:

- `KSWD(After_beating_Earl)` enables only:
  - `0x412C = 0x2904`
- `KSWD(Before_beating_Webster)` and `KSWD(After_beating_Webster)` additionally enable:
  - `0x4130 = 0x2A04`
  - `0x4134 = 0x2B04`
  - `0x4138 = 0x2C04`
  - `0x4140 = 0x2D04`
  - `0x4144 = 0x2E04`
  - `0x4148 = 0x3004`
  - `0x414C = 0x2F04`
  - `0x4158 = 0x3304`
  - `0x415C = 0x3404`
  - `0x4164 = 0x3704`
  - `0x4168 = 0x3804`
  - `0x4174 = 0x3A04`
  - `0x41D4 = 0x3604`
  - `0x41D8 = 0x3904`
  - `0x4258 = 0x3204`
  - `0x425C = 0x3104`
  - `0x4260 = 0x3504`
- `fixture-i(base_heat_level5)` matches the same late-state words for this family.

### Why it is still promising

- unaffected by:
  - `0x4038`-only rank-byte tests
  - `0x4040..0x4041` defeated-state/cache corruption
  - the false-lead keyed summary table patch
- compact and fixed-addressed, unlike the sliding keyed table
- clean late-stage enables line up with Webster-era progression rather than random save noise

### New proof-test pack

Prepared from clean `KSWD(Base)` by patching only the 2-byte state words:

- `local test pack: kswd_profile_entry_test`
  - `KSWD_entry_00_baseline`
  - `KSWD_entry_01_after_earl_single_412C`
  - `KSWD_entry_02_before_web_main_cluster`
  - `KSWD_entry_03_before_web_tail_cluster`
  - `KSWD_entry_04_before_web_combined`
  - `KSWD_entry_05_fixture-i_combined`

Cluster definitions:

- main cluster:
  - `0x412C`
  - `0x4130`
  - `0x4134`
  - `0x4138`
  - `0x4140`
  - `0x4144`
  - `0x4148`
  - `0x414C`
  - `0x4158`
  - `0x415C`
  - `0x4164`
  - `0x4168`
  - `0x4174`
  - `0x41D4`
  - `0x41D8`
- tail cluster:
  - `0x4258`
  - `0x425C`
  - `0x4260`

All variants were written through `SaveFile.save(...)` and validated `MD5/CRC1/CRC2 OK`.

## `kswd_profile_entry_test` outcome: fixed profile-entry family is not the unlock gate (2026-04-12)

In-game validation results for:

- `KSWD_entry_01_after_earl_single_412C`
- `KSWD_entry_02_before_web_main_cluster`
- `KSWD_entry_03_before_web_tail_cluster`
- `KSWD_entry_04_before_web_combined`
- `KSWD_entry_05_fixture-i_combined`

Observed behavior:

- all variants behaved exactly like baseline
- no visible change to:
  - current boss / challenge flow
  - dealership cars
  - cops / heat
  - performance upgrades
  - visual/body parts
  - paint

Practical interpretation:

- the fixed `0x412C..0x4260` entry family is not the normal parts/performance unlock gate
- it is either:
  - an inactive/unused profile table,
  - a companion table that requires another authoritative source,
  - or a non-shop layer with no visible effect in the tested contexts

This closes the current `0x412C..0x4260` hypothesis as another false lead.

## New sliding registry candidate at roughly `0x920..0xC1F` for normal performance unlocks (2026-04-12)

After closing the fixed-entry family, a stronger profile-level candidate remains in a
sliding table around `0x920..0xC1F`.

### Shape

- record stride: `0x14`
- aligned by stable 4-byte record id at offset `+0x04`
- practical starts per save:
  - `fixture-g`: `0x0920`
  - `KSWD(Base)` / `KSWD(Before_beating_Earl)`: `0x0940`
  - `KSWD(Before_beating_Webster)`: `0x0980`
  - `KSWD(After_beating_Webster)`: `0x0990`
  - `fixture-i(base_heat_level5)`: `0x0950`
- record layout:
  - `u16 a`
  - `u16 b`
  - `u32 id`
  - `u32 zero_or_unused`
  - `f32 e`
  - `f32 f`

### Why it is promising

- unlike prior false leads, this table is:
  - global profile-level data
  - not in car blocks
  - not in parts blocks
  - not in the keyed blacklist-summary layer
- it is also untouched by:
  - `0x4038`-only rank-byte tests
  - `0x4040..0x4041` defeated-state/cache corruption

### Clean ladder behavior

Compared with `KSWD(Base)`:

- baseline / `fixture-g`:
  - groups `b=2..8`: `a=0`, `f=0`
  - groups `b=9..15`: `a=5`, `f!=0`
- `KSWD(Before_beating_Webster)`:
  - groups `b=5..8` switch from:
    - `a=0 -> 5`
    - `f=0 -> non-zero`
  - groups `b=9..15` remain effectively active
- `KSWD(After_beating_Webster)`:
  - groups `b=4` switch to:
    - `a=3`
    - `f` stays `0`
  - groups `b=5..8` stay active (`a=5`, `f!=0`)
- `fixture-i(base_heat_level5)`:
  - groups `b=2..15` are active (`a=5`, `f!=0`)

This progression pattern is the closest match so far to a normal staged unlock registry:

- early save: only late/easy groups active
- mid-game: additional groups `5..8` activate
- later: group `4` transitions into a distinct current-state (`a=3`)
- endgame: everything down to `2` is active

### New proof-test pack

Prepared from clean `KSWD(Base)`:

- `local test pack: kswd_perf_registry_test`
  - `KSWD_perfreg_00_baseline`
  - `KSWD_perfreg_01_before_web_groups_5_8`
  - `KSWD_perfreg_02_after_web_groups_4_8`
  - `KSWD_perfreg_03_fixture-i_groups_2_8`
  - `KSWD_perfreg_04_fixture-i_full_registry`

Patch strategy:

- only records from this sliding registry are copied by aligned record index
- all story fields, cache fields, garage, cars, parts blocks, and keyed summary blocks remain untouched
- all variants validated `MD5/CRC1/CRC2 OK`

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

## 2026-04-12 - `kswd_perf_registry_test` failed; sliding registry is another summary/completion layer

- In-game validation results for:
  - `KSWD_perfreg_01_before_web_groups_5_8`
  - `KSWD_perfreg_02_after_web_groups_4_8`
  - `KSWD_perfreg_03_fixture-i_groups_2_8`
  - `KSWD_perfreg_04_fixture-i_full_registry`
- Result:
  - boss stayed baseline
  - dealership cars stayed baseline
  - cops / heat stayed baseline
  - performance stayed baseline
  - visual/body stayed baseline
  - career completion dropped from `36%` to `26%`
  - old blacklist rivals lost displayed race/milestone counters
- Refined interpretation:
  - the sliding registry near `0x920..0xC1F` is not the normal performance unlock gate
  - it is another presentation/progression-summary layer, likely tied to:
    - blacklist rival card counters
    - milestone lock presentation
    - career completion

## 2026-04-12 - New profile-tail candidate at `0x5620..0x57AF` plus `0x5B60..0x5B67`

After excluding:
- story/current-boss field `0x4038`
- sticky defeated cache `0x4040..0x4041`
- keyed blacklist summary table
- fixed entry family `0x412C..0x4260`
- sliding registry near `0x920..0xC1F`
- visual/body unlock subfamily around `0x55D0..0x55E7`

the strongest remaining clean progression candidate is a compact profile tail:
- main table: `0x5620..0x5737`
- small counters/tail: `0x5738..0x57AF`
- 8-byte marker block: `0x5B60..0x5B67`

### Clean ladder behavior

- `Before_beating_Vic`:
  - base table mostly `... FF 00`
  - marker cluster `0x56B1/0x56B5 = 3`
  - counters:
    - `0x5769 = 5`
    - `0x5771 = 1`
- `After_beating_Vic`:
  - local table flips near `0x56C9..0x56E6`
  - counters:
    - `0x5775 = 7`
    - `0x577D = 1`
    - `0x5781 = 0x0D`
    - `0x5789 = 1`
- `Before_beating_Earl`:
  - broad main-table activation:
    - repeating `0x..23/2B/33/.../73/.../B3/... = 2`
  - marker cluster `0x56B1/0x56B5 = 5`
  - marker byte `0x56B6 = 5`
- `After_beating_Earl`:
  - same Earl-era main table
  - marker byte `0x56B6 = FF`
  - counters:
    - `0x5769 = 4`
    - `0x5771 = 1`
    - `0x5775 = 0x0D`
    - `0x577D = 1`
- `Before_beating_Webster`:
  - broad main-table shift:
    - repeating `2 -> 1`
  - marker cluster `0x56B1/0x56B5 = 6`
  - marker byte `0x56B6 = FF`
  - counters:
    - `0x5769 = 4`
    - `0x5771 = 1`
    - `0x5775 = 0x14`
    - `0x577D = 1`
    - `0x5781 = 6`
    - `0x5789 = 1`
    - `0x578D = 5`
    - `0x5795 = 1`
- `After_beating_Webster`:
  - same main table as `Before_beating_Webster`
  - extra counter block:
    - `0x5799 = 4`
    - `0x57A1 = 1`
    - `0x57A5 = 9`
    - `0x57AD = 1`
- `fixture-i(base_heat_level5)`:
  - main table shifts one step further:
    - repeating `2 -> 0`
    - paired neighboring `0 -> 1` flips
  - counters:
    - `0x5769 = 0x14`
    - `0x5771 = 1`
    - `0x5781 = 0x15`
    - `0x5789 = 1`

### New proof-test pack

Prepared from clean `KSWD(Base)`:

- `local test pack: kswd_tail_unlock_test`
  - `KSWD_tail_00_baseline`
  - `KSWD_tail_01_before_web_main_5620_5737`
  - `KSWD_tail_02_before_web_tail_5738_57AF_and_5B60`
  - `KSWD_tail_03_before_web_combined`
  - `KSWD_tail_04_after_web_combined`
  - `KSWD_tail_05_fixture-i_combined`

Patch strategy:

- only this profile-tail candidate is copied
- `0x4038`, `0x4040..0x4041`, garage, cars, pursuit, parts blocks, and prior summary tables remain untouched
- all variants validated `MD5/CRC1/CRC2 OK`

## 2026-04-13 - `kswd_tail_unlock_test` is not the normal performance gate

- In-game validation results:
  - `KSWD_tail_01_before_web_main_5620_5737`:
    - full baseline
  - `KSWD_tail_02_before_web_tail_5738_57AF_and_5B60`:
    - baseline except backroom/unique performance packages changed
    - this matched direct per-car package changes, i.e. not the desired global shop gate
  - `KSWD_tail_03_before_web_combined`:
    - same as `tail-only`
  - `KSWD_tail_04_after_web_combined`:
    - same backroom/unique changes as above
    - plus extra `Parts -> Hoods`
    - plus `Visual -> Paint` and `Body Vinyls` opened fully (past `#8`)
  - `KSWD_tail_05_fixture-i_combined`:
    - same visual unlock expansion as `04`
    - no extra unique hood effect
- Refined interpretation:
  - `0x5620..0x5737` main table alone is not visibly authoritative
  - `0x5738..0x57AF` + `0x5B60..0x5B67` affect:
    - backroom / unique package availability
    - some visual/body subcategories
  - this family is still not the clean global `performance upgrades unlock` gate

## 2026-04-13 - New `8-byte` sliding table candidate at `0xC20..0xD57`

With prior false leads excluded, the next strongest remaining candidate is a compact
sliding table in `0xC20..0xD57`.

### Shape

- practical aligned list in clean saves uses `8-byte` records:
  - `u16 id`
  - `u16 kind` (always `4` in the aligned list)
  - `u16 x`
  - `u16 y`
- clean baseline (`KSWD(Base)`) aligned list:
  - starts at `0xC50`
  - length `0xA8` (`21` records)
  - marker tail at `0xD00..0xD17`
- later saves prepend extra records in front of the aligned list:
  - `Before_beating_Webster`: prelude `0xC20..0xC8F`, list `0xC90..0xD37`, markers `0xD40..0xD57`
  - `After_beating_Webster`: prelude `0xC20..0xC9F`, list `0xCA0..0xD47`, markers `0xD50..0xD67`
  - `fixture-i(base_heat_level5)`: list `0xC60..0xD07`, markers `0xD10..0xD27`

### Baseline aligned list (`KSWD(Base)`)

Aligned records in order:

- `20,4,0,0`
- `8,4,0,0`
- `19,4,0,0`
- `18,4,0,0`
- `4,4,0,0`
- `5,4,0,0`
- `15,4,4,3`
- `6,4,0,0`
- `1,4,0,0`
- `9,4,7,8`
- `2,4,0,0`
- `3,4,0,0`
- `16,4,0,0`
- `21,4,0,0`
- `13,4,5,7`
- `11,4,5,8`
- `14,4,5,6`
- `12,4,5,7`
- `10,4,7,8`
- `7,4,0,0`

### Clean ladder progression

- `Before_beating_Webster` aligned list differs from baseline by several IDs:
  - `8 -> (7,7)`
  - `5 -> (7,10)`
  - `6 -> (7,11)`
  - `9 -> (7,8)` unchanged from Earl-era baseline
  - `7 -> (7,10)`
- `After_beating_Webster` keeps the same late list, but also adds a prelude and shifted markers
- `fixture-i(base_heat_level5)` changes the aligned list more broadly:
  - `8 -> (7,5)`
  - `4 -> (7,8)`
  - `5 -> (7,8)`
  - `6 -> (7,7)`
  - `1 -> (7,11)`
  - `9 -> (7,5)`
  - `2 -> (7,8)`
  - `3 -> (7,8)`
  - `13 -> (5,4)`
  - `11 -> (5,5)`
  - `14 -> (5,4)`
  - `12 -> (5,5)`
  - `10 -> (7,5)`
  - `7 -> (7,7)`

### New proof-test pack

Prepared from clean `KSWD(Base)`:

- `local test pack: kswd_perf8_table_test`
  - `KSWD_perf8_00_baseline`
  - `KSWD_perf8_01_before_web_list_only`
  - `KSWD_perf8_02_before_web_prelude_only`
  - `KSWD_perf8_03_before_web_combined`
  - `KSWD_perf8_04_after_web_combined`
  - `KSWD_perf8_05_fixture-i_combined`

Patch strategy:

- `list_only` copies only the aligned `21 x 8-byte` list into the baseline list slot
- `prelude_only` copies only the source prelude into `0xC20..`
- `combined` copies:
  - prelude
  - aligned list
  - trailing marker records
- all story/cache/garage/car/parts-block/keyed-summary/summary-registry data remain untouched
- all variants validated `MD5/CRC1/CRC2 OK`

## 2026-04-13 - Career garage crash root cause: partially dirty pursuit slots, not `0x5577`

In-game reproduction on `fixture-g` narrowed the remaining crash to `Career`-linked Blacklist cars:

- after fixing injected Blacklist records from `0x02` to `0x42`, `My Cars` variants loaded fine
- the same cars still crashed in `Career` during `Car Select` / `Free Roam`
- copying donor `fixture-e` table `0x5577` into `fixture-g` did **not** change the crash behavior

The decisive diff came from raw pursuit-slot inspection at `0xE2ED`:

- some reusable tail slots already contained structurally dirty garage records before injection
- example on `fixture-g.bak_20260413_204918`:
  - slot `2`: first byte stayed `0xFF` instead of slot id `0x02`
  - slot `2`: heat float stayed `0.27070346` (`A5 99 8A 3E`) instead of baseline `1.0`
  - slot `4`: first byte stayed `0xFF`
  - slot `4`: heat float stayed `0.0`
- after Blacklist injection, new `Career` / `Pink Slip` owned records were linked to these partially dirty pursuit slots

Why `My Cars` stayed safe:

- `My Cars` cars do not use the linked pursuit/garage slot path during garage rotation
- `Career` cars do, so the game consumed the malformed `0xE2ED` payload and crashed

Root cause in editor logic:

- `clear_pursuit_slot(...)` only zeroed selected fields (`heat`, `bounty`, `escaped`, `busted`)
- it did **not** fully canonicalize an already-detected dirty slot
- if a slot passed `_is_garage_slot(...)` but still carried placeholder-style garbage (`raw[0] = 0xFF`, bad heat float), the injector reused it as-is

Fix:

- `clear_pursuit_slot(...)` now rewrites the entire `0x38` pursuit record using `_build_zero_pursuit_slot_payload(...)`
- this guarantees:
  - byte `0` = actual `career_slot`
  - valid garage signatures
  - baseline heat `1.0`
  - zero bounty / escape / bust values

Validation outcome:

- after normalizing the linked pursuit slots in `fixture-g`, `Career garage` scrolling across the full range stopped crashing
- `Free Roam` load also stopped crashing on the same save
- practical conclusion: the remaining crash was caused by malformed pursuit-slot state, not by unresolved visual table `0x5577`
