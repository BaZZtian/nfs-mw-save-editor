from __future__ import annotations

from typing import Dict, Optional

PERF_PART_NAMES = ("Tires", "Brakes", "Suspension", "Transmission", "Engine", "Turbo", "NOS")

_EARLY_TIER_LIMITS: Dict[str, int] = {
    "Tires": 3,
    "Brakes": 4,
    "Suspension": 3,
    "Transmission": 4,
    "Engine": 4,
    "Turbo": 3,
    "NOS": 3,
}

_MID_TIER_LIMITS: Dict[str, int] = {
    "Tires": 2,
    "Brakes": 3,
    "Suspension": 2,
    "Transmission": 3,
    "Engine": 3,
    "Turbo": 2,
    "NOS": 3,
}

_HIGH_TIER_LIMITS: Dict[str, int] = {
    "Tires": 2,
    "Brakes": 2,
    "Suspension": 1,
    "Transmission": 2,
    "Engine": 2,
    "Turbo": 1,
    "NOS": 3,
}

_EXOTIC_TIER_LIMITS: Dict[str, int] = {
    "Tires": 1,
    "Brakes": 1,
    "Suspension": 1,
    "Transmission": 1,
    "Engine": 1,
    "Turbo": 1,
    "NOS": 3,
}


def _copy_limits(source: Dict[str, int]) -> Dict[str, int]:
    return dict(source)


MODEL_TUNING_LIMITS: Dict[str, Dict[str, int]] = {
    "Audi A3 Quattro": _copy_limits(_EARLY_TIER_LIMITS),
    "Audi A4 Quattro": _copy_limits(_EARLY_TIER_LIMITS),
    "Audi TT Quattro": _copy_limits(_EARLY_TIER_LIMITS),
    "Cadillac CTS": _copy_limits(_EARLY_TIER_LIMITS),
    "Chevrolet Cobalt SS": _copy_limits(_EARLY_TIER_LIMITS),
    "Fiat Punto": _copy_limits(_EARLY_TIER_LIMITS),
    "Lexus IS300": _copy_limits(_EARLY_TIER_LIMITS),
    "Mazda RX-8": _copy_limits(_EARLY_TIER_LIMITS),
    "Mercedes SL 500": _copy_limits(_EARLY_TIER_LIMITS),
    "Mitsubishi Eclipse": _copy_limits(_EARLY_TIER_LIMITS),
    "Renault Clio V6": _copy_limits(_EARLY_TIER_LIMITS),
    "Toyota Supra": _copy_limits(_EARLY_TIER_LIMITS),
    "VW Golf GTI": _copy_limits(_EARLY_TIER_LIMITS),
    "Ford Mustang GT": _copy_limits(_MID_TIER_LIMITS),
    "Lotus Elise": _copy_limits(_MID_TIER_LIMITS),
    "Mercedes CLK 500": _copy_limits(_MID_TIER_LIMITS),
    "Mazda RX-7": _copy_limits(_MID_TIER_LIMITS),
    "Mitsubishi Lancer EVO VIII": _copy_limits(_MID_TIER_LIMITS),
    "Pontiac GTO": _copy_limits(_MID_TIER_LIMITS),
    "Porsche 911 Carrera S": _copy_limits(_MID_TIER_LIMITS),
    "Porsche Cayman S": _copy_limits(_MID_TIER_LIMITS),
    "Subaru Impreza WRX STI": _copy_limits(_MID_TIER_LIMITS),
    "Vauxhall Monaro VXR": _copy_limits(_MID_TIER_LIMITS),
    "Aston Martin DB9": _copy_limits(_MID_TIER_LIMITS),
    "Corvette C6": _copy_limits(_HIGH_TIER_LIMITS),
    "Dodge Viper SRT10": _copy_limits(_HIGH_TIER_LIMITS),
    "Lamborghini Gallardo": _copy_limits(_HIGH_TIER_LIMITS),
    "Porsche 911 Turbo S": _copy_limits(_HIGH_TIER_LIMITS),
    "Ford GT": _copy_limits(_EXOTIC_TIER_LIMITS),
    "Lamborghini Murcielago": _copy_limits(_EXOTIC_TIER_LIMITS),
    "Mercedes SLR McLaren": _copy_limits(_EXOTIC_TIER_LIMITS),
    "Porsche Carrera GT": _copy_limits(_EXOTIC_TIER_LIMITS),
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
