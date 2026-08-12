from __future__ import annotations

from typing import Dict, Optional


def _sig(hex_bytes: str) -> bytes:
    return bytes.fromhex(hex_bytes)


# Signature = lookup2(FE model name) + lookup2(vehicle model name), both u32 LE.
# Values are derived from vanilla PC v1.3 model names and verified against
# their lookup2 hashes; internal names remain beside entries for provenance.
# Signature provenance: cparty & Zhoul, CE forum ~2005.
CAR_SIGNATURES: Dict[bytes, str] = {
    # --- player / event cars (42) ---
    _sig("6A 1C B6 A4 6A 1C B6 A4"): "Aston Martin DB9",  # db9 / db9
    _sig("7B C1 72 7B E5 14 C4 D5"): "Audi A3 Quattro",  # a3_20t / a3
    _sig("7B 4B F6 F8 BF 42 7E 9B"): "Audi A4 Quattro",  # a4_32 / a4
    _sig("C8 8B 3A 19 C8 8B 3A 19"): "Audi TT Quattro",  # tt / tt
    _sig("4E 4A CC 23 B3 5F 08 4E"): "BMW M3 GTR",  # m3_gtre46 / bmwm3gtre46
    _sig("4E 4A CC 23 F8 E0 DA 39"): "BMW M3 GTR (slow version)",  # m3_gtre46 / m3gtre46careerstart
    _sig("A6 FE C2 81 8B EB 23 4C"): "BMW M3 GTR (speed test)",  # m3_gtr / speedtest
    _sig("A6 FE C2 81 3F 08 88 CD"): "BMW M3 Street Version",  # m3_gtr / bmwm3gtr
    _sig("20 65 18 DF 20 65 18 DF"): "Cadillac CTS",  # cts / cts
    _sig("19 45 94 90 19 45 94 90"): "Chevrolet Camaro SS",  # camaro / camaro
    _sig("95 40 78 5A 95 40 78 5A"): "Chevrolet Cobalt SS",  # cobaltss / cobaltss
    _sig("CF 82 E5 22 E4 8C 11 46"): "Corvette C6",  # corvette_car / corvette
    _sig("9E 57 65 01 9E 57 65 01"): "Corvette C6.R",  # corvettec6r / corvettec6r
    _sig("08 D4 BE 6E 08 D4 BE 6E"): "Dodge Viper SRT10",  # viper / viper
    _sig("11 7A EE A6 11 7A EE A6"): "Fiat Punto",  # punto / punto
    _sig("EA A5 C0 42 EA A5 C0 42"): "Ford GT",  # fordgt / fordgt
    _sig("4D FD 93 9B 4D FD 93 9B"): "Ford Mustang GT",  # mustanggt / mustanggt
    _sig("4D FD 93 9B 64 5F DC F9"): "Ford Mustang GT (demo)",  # mustanggt / mustang_demo
    _sig("0B C4 2C 7B 0B C4 2C 7B"): "Lamborghini Gallardo",  # gallardo / gallardo
    _sig("EB 77 CD C1 EB 77 CD C1"): "Lamborghini Murcielago",  # murcielago / murcielago
    _sig("B0 2F FF 5B B0 2F FF 5B"): "Lexus IS300",  # is300 / is300
    _sig("36 49 3D 31 36 49 3D 31"): "Lotus Elise",  # elise / elise
    _sig("33 C8 09 8E 33 C8 09 8E"): "Mazda RX-7",  # rx7 / rx7
    _sig("37 44 33 D6 37 44 33 D6"): "Mazda RX-8",  # rx8 / rx8
    _sig("5B 98 2F BD D9 3C 12 72"): "Mazda RX-8 (speed test)",  # rx8speed / rx8speedt
    _sig("2F AF 77 82 2F AF 77 82"): "Mercedes CLK 500",  # clk500 / clk500
    _sig("BB B5 00 A8 BB B5 00 A8"): "Mercedes SL 500",  # sl500 / sl500
    _sig("A1 F9 47 71 A1 F9 47 71"): "Mercedes SL65 AMG",  # sl65 / sl65
    _sig("BB D9 2A E3 BB D9 2A E3"): "Mercedes SLR McLaren",  # slr / slr
    _sig("BD 0B D7 A2 BD 0B D7 A2"): "Mitsubishi Eclipse",  # eclipsegt / eclipsegt
    _sig("B6 FB EE CC B6 FB EE CC"): "Mitsubishi Lancer EVO VIII",  # lancerevo8 / lancerevo8
    _sig("C6 3D 48 AA C6 3D 48 AA"): "Pontiac GTO",  # gto / gto
    _sig("DA A7 4D 3C DA A7 4D 3C"): "Porsche 911 Carrera S",  # 997s / 997s
    _sig("6F F4 3E 9B 6F F4 3E 9B"): "Porsche 911 GT2",  # 911gt2 / 911gt2
    _sig("8D 5B 7D D2 8D 5B 7D D2"): "Porsche 911 Turbo S",  # 911turbo / 911turbo
    _sig("92 99 86 C4 D4 3D 06 67"): "Porsche Carrera GT",  # carrera_gt / carreragt
    _sig("EB 5B 55 41 EB 5B 55 41"): "Porsche Cayman S",  # caymans / caymans
    _sig("EB 67 18 EB EB 67 18 EB"): "Renault Clio V6",  # clio / clio
    _sig("34 89 8C 19 0D 56 3B 5F"): "Subaru Impreza WRX STI",  # imprezzawrx / imprezawrx
    _sig("34 34 F1 66 34 34 F1 66"): "Toyota Supra",  # supra / supra
    _sig("53 4B 05 79 53 4B 05 79"): "VW Golf GTI",  # gti / gti
    _sig("A1 E1 D3 D8 A1 E1 D3 D8"): "Vauxhall Monaro VXR",  # monaro / monaro
    # --- cops, traffic, cutscene stand-ins (59) ---
    _sig("AF 2D C3 C1 F5 F7 67 6F"): "Ambulance",  # vehicles / trafamb
    _sig("AF 2D C3 C1 6A 4D 33 46"): "Cement Truck",  # vehicles / trafcemtr
    _sig("AF 2D C3 C1 FA FF D9 51"): "Cement Truck (cutscene)",  # vehicles / cs_trafcement
    _sig("AF 2D C3 C1 82 D1 A1 A3"): "Cop (ghost)",  # vehicles / copghost
    _sig("AF 2D C3 C1 0C 07 6C 8F"): "Cop Corvette (cutscene)",  # vehicles / cs_c6_copsporthench
    _sig("AF 2D C3 C1 88 66 EB A4"): "Cop Corvette (ghost)",  # vehicles / copsportghost
    _sig("AF 2D C3 C1 E2 2F F3 B2"): "Cop Corvette (henchman)",  # vehicles / copsporthench
    _sig("AF 2D C3 C1 CB CC 49 7A"): "Cop Corvette (undercover)",  # vehicles / copsport
    _sig("AF 2D C3 C1 38 29 9B BB"): "Cop Cruiser",  # vehicles / copmidsize
    _sig("AF 2D C3 C1 54 3E 6E 5D"): "Cop Cruiser (NIS LD)",  # vehicles / copmidsize_nis_ld
    _sig("AF 2D C3 C1 B7 AC 37 95"): "Cop Cruiser (NIS)",  # vehicles / copmidsize_nis
    _sig("AF 2D C3 C1 F5 7E 66 70"): "Cop Cruiser (cutscene)",  # vehicles / cs_viper_copmidsize
    _sig("AF 2D C3 C1 56 53 98 CC"): "Cop GTO",  # vehicles / copgto
    _sig("AF 2D C3 C1 95 DC 49 69"): "Cop GTO (cutscene)",  # vehicles / cs_gto_copgto
    _sig("AF 2D C3 C1 F6 1D EC E9"): "Cop GTO (ghost)",  # vehicles / copgtoghost
    _sig("AF 2D C3 C1 26 82 B3 38"): "Cop SUV",  # vehicles / copsuv
    _sig("AF 2D C3 C1 AE 75 E6 28"): "Cop SUV (cutscene)",  # vehicles / cs_mustang_copsuv
    _sig("AF 2D C3 C1 38 0E B1 54"): "Cop SUV (light)",  # vehicles / copsuvl
    _sig("AF 2D C3 C1 AC 9E 14 2E"): "Cop SUV (patrol)",  # vehicles / copsuvpatrol
    _sig("AF 2D C3 C1 36 88 7C E6"): "Courier Van",  # vehicles / trafcourt
    _sig("AF 2D C3 C1 6D 80 7C D3"): "Cross' Corvette",  # vehicles / copcross
    _sig("AF 2D C3 C1 39 13 6C C5"): "Dumptruck",  # vehicles / trafdmptr
    _sig("AF 2D C3 C1 E0 EC C7 08"): "Fire Truck",  # vehicles / traffire
    _sig("AF 2D C3 C1 64 5F DC F9"): "Ford Mustang GT (demo)",  # vehicles / mustang_demo
    _sig("AF 2D C3 C1 94 1A 36 CC"): "Garbage Truck",  # vehicles / trafgarb
    _sig("AF 2D C3 C1 C7 1A 47 A7"): "Garbage Truck (cutscene)",  # vehicles / cs_trafgarb
    _sig("AF 2D C3 C1 E9 BE D4 E6"): "Minivan",  # vehicles / trafminivan
    _sig("AF 2D C3 C1 D8 E0 EC 71"): "Minivan (cutscene)",  # vehicles / cs_cts_traf_minivan
    _sig("AF 2D C3 C1 72 3C B9 DB"): "News Van",  # vehicles / trafnews
    _sig("AF 2D C3 C1 DD 89 BE 7D"): "Pickup Truck",  # vehicles / trafpickupa
    _sig("AF 2D C3 C1 26 29 AF EB"): "Pizza Car",  # vehicles / trafpizza
    _sig("AF 2D C3 C1 4B C7 F2 C5"): "Pizza Car (cutscene)",  # vehicles / cs_clio_trafpizza
    _sig("AF 2D C3 C1 B2 5E 46 06"): "Police Helicopter",  # vehicles / copheli
    _sig("AF 2D C3 C1 D9 16 9B DF"): "Sedan A",  # vehicles / traf4dseda
    _sig("AF 2D C3 C1 23 29 2B 66"): "Sedan B",  # vehicles / traf4dsedb
    _sig("AF 2D C3 C1 56 87 C9 5E"): "Sedan C",  # vehicles / traf4dsedc
    _sig("AF 2D C3 C1 BA 48 0B D5"): "Semi Truck",  # vehicles / semi
    _sig("AF 2D C3 C1 C2 E7 27 C0"): "Semi Truck (cement)",  # vehicles / semicmt
    _sig("AF 2D C3 C1 FA FA 0D 25"): "Semi Truck (container)",  # vehicles / semicon
    _sig("AF 2D C3 C1 21 3B F9 E8"): "Semi Truck (crates)",  # vehicles / semicrate
    _sig("AF 2D C3 C1 46 DF 7E 34"): "Semi Truck (cutscene)",  # vehicles / cs_semi
    _sig("AF 2D C3 C1 67 CC 92 0A"): "Semi Truck (logs)",  # vehicles / semilog
    _sig("AF 2D C3 C1 2C 5C 4D DD"): "Semi Truck A",  # vehicles / semia
    _sig("AF 2D C3 C1 C4 09 B5 A9"): "Semi Truck B",  # vehicles / semib
    _sig("AF 2D C3 C1 C3 4B CE 43"): "Station Wagon",  # vehicles / trafstwag
    _sig("AF 2D C3 C1 9E 78 01 D6"): "Taxi",  # vehicles / traftaxi
    _sig("AF 2D C3 C1 F1 1A F0 7A"): "Taxi (cutscene)",  # vehicles / cs_clio_traftaxi
    _sig("AF 2D C3 C1 21 16 45 68"): "Traffic Camper",  # vehicles / trafcamper
    _sig("AF 2D C3 C1 88 34 1A 53"): "Traffic Coupe",  # vehicles / trafficcoup
    _sig("AF 2D C3 C1 59 BB C7 A0"): "Traffic Hatchback",  # vehicles / trafha
    _sig("AF 2D C3 C1 90 A0 8E 3E"): "Traffic SUV",  # vehicles / trafsuva
    _sig("AF 2D C3 C1 49 39 3B 74"): "Traffic Truck (cutscene)",  # vehicles / cs_cts_traffictruck
    _sig("AF 2D C3 C1 7A AF E7 53"): "Traffic Van",  # vehicles / trafvanb
    _sig("AF 2D C3 C1 46 FA 0D 37"): "Trailer (cement)",  # vehicles / trailercmt
    _sig("AF 2D C3 C1 31 AA C6 45"): "Trailer (container)",  # vehicles / trailercon
    _sig("AF 2D C3 C1 C6 61 EE A0"): "Trailer (crates)",  # vehicles / trailercrate
    _sig("AF 2D C3 C1 9E F7 FB DC"): "Trailer (logs)",  # vehicles / trailerlog
    _sig("AF 2D C3 C1 8A 2F D8 00"): "Trailer A",  # vehicles / trailera
    _sig("AF 2D C3 C1 90 5B AA 1C"): "Trailer B",  # vehicles / trailerb
}


def resolve_car_name(signature: bytes) -> Optional[str]:
    return CAR_SIGNATURES.get(bytes(signature))


def format_signature(signature: bytes) -> str:
    return bytes(signature).hex(" ").upper()
