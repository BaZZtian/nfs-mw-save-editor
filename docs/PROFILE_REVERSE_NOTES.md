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
- how current car / active career car is marked in these structures

Current fallback policy:
- if a future save has no unique car-record match for a pursuit slot, the UI should
  show an honest fallback instead of guessing a vehicle name

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
