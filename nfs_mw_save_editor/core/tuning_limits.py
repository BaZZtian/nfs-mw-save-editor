"""Per-model perf tuning caps = the game's own upgrade ladders.

GENERATED FILE - regenerate with RE/tools/gen_tuning_limits.py, do not
edit rows by hand. Source: the seven *_upgrades step counts in each car's
pvehicle collection layout in GLOBAL/attributes.bin, one row per display
name the editor can produce (core/cars.py signatures; the vehicle half of
a signature IS the pvehicle collection key).

Reading a row: an all-zero row is game truth - that car has no upgrade
ladder at all (911 GT2 is the only player car like this); race/bonus cars
are nos-only (0/0/0/0/0/0/3). A model absent from this dict has no
pvehicle record in the vault and get_model_tuning_limits() returns None
("no confirmed caps"), which keeps perf editing locked for it.

Validation chain (2026-07-17): frozen empirical March table matches the vault
32/32; triple lock min(presetride, ladder) == save pending-build packages
on all 28 slots (see RE/tools/dump_upgrade_ladders.py gates).
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

PERF_PART_NAMES = ("Tires", "Brakes", "Suspension", "Transmission", "Engine", "Turbo", "NOS")

# model -> (tires, brakes, suspension, transmission, engine, turbo, nos)
_MODEL_LADDERS: Dict[str, Tuple[int, ...]] = {
    # --- player / event cars (42) ---
    "Aston Martin DB9": (2, 3, 2, 3, 3, 2, 3),
    "Audi A3 Quattro": (3, 4, 3, 4, 4, 3, 3),
    "Audi A4 Quattro": (3, 4, 3, 4, 4, 3, 3),
    "Audi TT Quattro": (3, 4, 3, 4, 4, 3, 3),
    "BMW M3 GTR": (0, 0, 0, 0, 0, 0, 3),
    "BMW M3 GTR (slow version)": (0, 0, 0, 0, 0, 0, 3),
    "BMW M3 GTR (speed test)": (0, 0, 0, 0, 0, 0, 0),
    "BMW M3 Street Version": (0, 0, 0, 0, 0, 0, 3),
    "Cadillac CTS": (3, 4, 3, 4, 4, 3, 3),
    "Chevrolet Camaro SS": (0, 0, 0, 0, 0, 0, 3),
    "Chevrolet Cobalt SS": (3, 4, 3, 4, 4, 3, 3),
    "Corvette C6": (2, 2, 1, 2, 2, 1, 3),
    "Corvette C6.R": (0, 0, 0, 0, 0, 0, 3),
    "Dodge Viper SRT10": (2, 2, 1, 2, 2, 1, 3),
    "Fiat Punto": (3, 4, 3, 4, 4, 3, 3),
    "Ford GT": (1, 1, 1, 1, 1, 1, 3),
    "Ford Mustang GT": (2, 3, 2, 3, 3, 2, 3),
    "Ford Mustang GT (demo)": (0, 0, 0, 0, 0, 0, 3),
    "Lamborghini Gallardo": (2, 2, 1, 2, 2, 1, 3),
    "Lamborghini Murcielago": (1, 1, 1, 1, 1, 1, 3),
    "Lexus IS300": (3, 4, 3, 4, 4, 3, 3),
    "Lotus Elise": (2, 3, 2, 3, 3, 2, 3),
    "Mazda RX-7": (2, 3, 2, 3, 3, 2, 3),
    "Mazda RX-8": (3, 4, 3, 4, 4, 3, 3),
    "Mazda RX-8 (speed test)": (3, 4, 3, 4, 4, 3, 3),
    "Mercedes CLK 500": (2, 3, 2, 3, 3, 2, 3),
    "Mercedes SL 500": (3, 4, 3, 4, 4, 3, 3),
    "Mercedes SL65 AMG": (0, 0, 0, 0, 0, 0, 3),
    "Mercedes SLR McLaren": (1, 1, 1, 1, 1, 1, 3),
    "Mitsubishi Eclipse": (3, 4, 3, 4, 4, 3, 3),
    "Mitsubishi Lancer EVO VIII": (2, 3, 2, 3, 3, 2, 3),
    "Pontiac GTO": (2, 3, 2, 3, 3, 2, 3),
    "Porsche 911 Carrera S": (2, 3, 2, 3, 3, 2, 3),
    "Porsche 911 GT2": (0, 0, 0, 0, 0, 0, 0),
    "Porsche 911 Turbo S": (2, 2, 1, 2, 2, 1, 3),
    "Porsche Carrera GT": (1, 1, 1, 1, 1, 1, 3),
    "Porsche Cayman S": (2, 3, 2, 3, 3, 2, 3),
    "Renault Clio V6": (3, 4, 3, 4, 4, 3, 3),
    "Subaru Impreza WRX STI": (2, 3, 2, 3, 3, 2, 3),
    "Toyota Supra": (3, 4, 3, 4, 4, 3, 3),
    "VW Golf GTI": (3, 4, 3, 4, 4, 3, 3),
    "Vauxhall Monaro VXR": (2, 3, 2, 3, 3, 2, 3),
    # --- cops, traffic, cutscene stand-ins (58) ---
    "Ambulance": (0, 0, 0, 0, 0, 0, 0),
    "Cement Truck": (0, 0, 0, 0, 0, 0, 0),
    "Cement Truck (cutscene)": (0, 0, 0, 0, 0, 0, 0),
    "Cop (ghost)": (0, 0, 0, 0, 0, 0, 0),
    "Cop Corvette (cutscene)": (0, 0, 0, 0, 0, 0, 3),
    "Cop Corvette (ghost)": (0, 0, 0, 0, 0, 0, 0),
    "Cop Corvette (henchman)": (0, 0, 0, 0, 0, 0, 0),
    "Cop Corvette (undercover)": (0, 0, 0, 0, 0, 0, 0),
    "Cop Cruiser": (0, 0, 0, 0, 0, 0, 0),
    "Cop Cruiser (NIS LD)": (0, 0, 0, 0, 0, 0, 0),
    "Cop Cruiser (NIS)": (0, 0, 0, 0, 0, 0, 0),
    "Cop Cruiser (cutscene)": (2, 2, 1, 2, 2, 1, 3),
    "Cop GTO": (0, 0, 0, 0, 0, 0, 0),
    "Cop GTO (cutscene)": (2, 3, 2, 3, 3, 2, 3),
    "Cop GTO (ghost)": (0, 0, 0, 0, 0, 0, 0),
    "Cop SUV": (0, 0, 0, 0, 0, 0, 0),
    "Cop SUV (cutscene)": (2, 3, 2, 3, 3, 2, 3),
    "Cop SUV (light)": (0, 0, 0, 0, 0, 0, 0),
    "Cop SUV (patrol)": (0, 0, 0, 0, 0, 0, 0),
    "Courier Van": (0, 0, 0, 0, 0, 0, 0),
    "Cross' Corvette": (0, 0, 0, 0, 0, 0, 0),
    "Dumptruck": (0, 0, 0, 0, 0, 0, 0),
    "Fire Truck": (0, 0, 0, 0, 0, 0, 0),
    "Garbage Truck": (0, 0, 0, 0, 0, 0, 0),
    "Garbage Truck (cutscene)": (0, 0, 0, 0, 0, 0, 0),
    "Minivan": (0, 0, 0, 0, 0, 0, 0),
    "Minivan (cutscene)": (0, 0, 0, 0, 0, 0, 0),
    "News Van": (0, 0, 0, 0, 0, 0, 0),
    "Pickup Truck": (0, 0, 0, 0, 0, 0, 0),
    "Pizza Car": (0, 0, 0, 0, 0, 0, 0),
    "Pizza Car (cutscene)": (0, 0, 0, 0, 0, 0, 0),
    "Police Helicopter": (0, 0, 0, 0, 0, 0, 0),
    "Sedan A": (0, 0, 0, 0, 0, 0, 0),
    "Sedan B": (0, 0, 0, 0, 0, 0, 0),
    "Sedan C": (0, 0, 0, 0, 0, 0, 0),
    "Semi Truck": (0, 0, 0, 0, 0, 0, 0),
    "Semi Truck (cement)": (0, 0, 0, 0, 0, 0, 0),
    "Semi Truck (container)": (0, 0, 0, 0, 0, 0, 0),
    "Semi Truck (crates)": (0, 0, 0, 0, 0, 0, 0),
    "Semi Truck (cutscene)": (0, 0, 0, 0, 0, 0, 0),
    "Semi Truck (logs)": (0, 0, 0, 0, 0, 0, 0),
    "Semi Truck A": (0, 0, 0, 0, 0, 0, 0),
    "Semi Truck B": (0, 0, 0, 0, 0, 0, 0),
    "Station Wagon": (0, 0, 0, 0, 0, 0, 0),
    "Taxi": (0, 0, 0, 0, 0, 0, 0),
    "Taxi (cutscene)": (0, 0, 0, 0, 0, 0, 0),
    "Traffic Camper": (0, 0, 0, 0, 0, 0, 0),
    "Traffic Coupe": (0, 0, 0, 0, 0, 0, 0),
    "Traffic Hatchback": (0, 0, 0, 0, 0, 0, 0),
    "Traffic SUV": (0, 0, 0, 0, 0, 0, 0),
    "Traffic Truck (cutscene)": (0, 0, 0, 0, 0, 0, 0),
    "Traffic Van": (0, 0, 0, 0, 0, 0, 0),
    "Trailer (cement)": (0, 0, 0, 0, 0, 0, 0),
    "Trailer (container)": (0, 0, 0, 0, 0, 0, 0),
    "Trailer (crates)": (0, 0, 0, 0, 0, 0, 0),
    "Trailer (logs)": (0, 0, 0, 0, 0, 0, 0),
    "Trailer A": (0, 0, 0, 0, 0, 0, 0),
    "Trailer B": (0, 0, 0, 0, 0, 0, 0),
}

MODEL_TUNING_LIMITS: Dict[str, Dict[str, int]] = {
    model: dict(zip(PERF_PART_NAMES, ladder))
    for model, ladder in _MODEL_LADDERS.items()
}


def get_model_tuning_limits(model_name: str) -> Optional[Dict[str, int]]:
    limits = MODEL_TUNING_LIMITS.get(str(model_name))
    if limits is None:
        return None
    return dict(limits)


def get_tuning_limit(model_name: str, part_name: str, default: int = 4) -> int:
    limits = MODEL_TUNING_LIMITS.get(str(model_name))
    if limits is None:
        return int(default)
    return int(limits.get(str(part_name), default))
