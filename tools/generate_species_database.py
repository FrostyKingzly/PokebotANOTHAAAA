"""Generate the consolidated ``pokemon_species.json`` file from PokeAPI CSV dumps.

This helper keeps the runtime SpeciesDatabase lightweight by emitting a single
JSON document that contains the most commonly used species attributes:

* National Dex number
* English display name
* Typing
* Base stats
* Ability slots (primary/secondary/hidden)
* Growth rate, capture rate, base experience, height, weight
* Gender ratio
* Flavor text description (latest English entry)

The source CSVs are cached in ``pokeapi_csv_bot/`` inside the repository. Run
this script anytime those inputs are updated to refresh ``data/pokemon_species.json``.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "pokeapi_csv_bot"
OUTPUT_PATH = ROOT / "data" / "pokemon_species.json"


def _load_csv(name: str) -> List[Dict[str, str]]:
    path = CSV_DIR / name
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows: List[Dict[str, str]] = []
        for row in reader:
            normalized = {key.lstrip("\ufeff"): value for key, value in row.items()}
            rows.append(normalized)
        return rows


def _gender_ratio(rate: int) -> Dict[str, float]:
    """Convert PokeAPI gender rate to percentage split.

    PokeAPI stores gender rate as the number of female slots out of 8, with -1
    representing genderless species.
    """

    if rate < 0:
        return {"male": 0.0, "female": 0.0}

    female = round(rate * 12.5, 1)
    male = round(100 - female, 1)
    return {"male": male, "female": female}


def _clean_flavor(text: str) -> str:
    """Normalize flavor text into a single line."""

    return " ".join(text.replace("\f", " ").replace("\n", " ").split())


def build_species_payload() -> Dict[str, Dict]:
    """Assemble the combined species mapping keyed by dex number."""

    pokedex_rows = _load_csv("pokedexes.csv")
    national_id = next(int(r["id"]) for r in pokedex_rows if r["identifier"] == "national")

    dex_numbers = {}
    for row in _load_csv("pokemon_dex_numbers.csv"):
        if int(row["pokedex_id"]) != national_id:
            continue
        dex_numbers[int(row["species_id"])] = int(row["pokedex_number"])

    species_rows = {int(r["id"]): r for r in _load_csv("pokemon_species.csv")}
    species_names: Dict[int, str] = {}
    species_genus: Dict[int, str] = {}
    for row in _load_csv("pokemon_species_names.csv"):
        if row.get("local_language_id") != "9":
            continue
        sid = int(row["pokemon_species_id"])
        species_names[sid] = row.get("name") or species_rows.get(sid, {}).get("identifier", "").title()
        species_genus[sid] = row.get("genus") or ""

    growth_rates = {int(r["id"]): r["identifier"] for r in _load_csv("growth_rates.csv")}
    type_lookup = {int(r["id"]): r["identifier"] for r in _load_csv("types.csv")}
    stat_lookup = {int(r["id"]): r["identifier"] for r in _load_csv("stats.csv")}
    ability_lookup = {int(r["id"]): r["identifier"] for r in _load_csv("abilities.csv")}

    default_pokemon: Dict[int, Dict[str, str]] = {}
    for row in _load_csv("pokemon.csv"):
        if row.get("is_default") == "1":
            default_pokemon[int(row["species_id"])] = row

    pokemon_types = _load_csv("pokemon_types.csv")
    pokemon_stats = _load_csv("pokemon_stats.csv")
    pokemon_abilities = _load_csv("pokemon_abilities.csv")

    # Capture the most recent English flavor text entry per species
    flavor_texts: Dict[int, str] = {}
    flavor_versions: Dict[int, int] = {}
    for row in _load_csv("pokemon_species_flavor_text.csv"):
        if row.get("language_id") != "9":
            continue

        sid = int(row["species_id"])
        version_id = int(row.get("version_id", 0))
        if sid not in flavor_versions or version_id >= flavor_versions[sid]:
            flavor_versions[sid] = version_id
            flavor_texts[sid] = _clean_flavor(row.get("flavor_text", "").strip())

    species_payload: Dict[str, Dict] = {}

    for species_id, row in species_rows.items():
        dex_number = dex_numbers.get(species_id)
        default_row = default_pokemon.get(species_id)
        if dex_number is None or default_row is None:
            continue

        base_stats: Dict[str, int] = {}
        for stat_row in pokemon_stats:
            if int(stat_row["pokemon_id"]) != int(default_row["id"]):
                continue

            stat_name = stat_lookup.get(int(stat_row["stat_id"]))
            if not stat_name:
                continue

            key = stat_name.replace("special-attack", "sp_attack").replace("special-defense", "sp_defense")
            key = key.replace("special_attack", "sp_attack").replace("special_defense", "sp_defense")
            base_stats[key] = int(stat_row["base_stat"])

        type_entries = [
            t for t in pokemon_types if int(t["pokemon_id"]) == int(default_row["id"])
        ]
        type_entries.sort(key=lambda t: int(t.get("slot", 0)))
        types = [type_lookup.get(int(t["type_id"])) for t in type_entries if int(t["type_id"]) in type_lookup]

        ability_entries = [
            a for a in pokemon_abilities if int(a["pokemon_id"]) == int(default_row["id"])
        ]
        ability_entries.sort(key=lambda a: int(a.get("slot", 0)))
        abilities = {"primary": None, "secondary": None, "hidden": None}
        for ability_row in ability_entries:
            ability_name = ability_lookup.get(int(ability_row["ability_id"]))
            if not ability_name:
                continue

            if ability_row.get("is_hidden") == "1":
                abilities["hidden"] = ability_name
            else:
                slot = ability_row.get("slot")
                if slot == "1":
                    abilities["primary"] = ability_name
                elif slot == "2":
                    abilities["secondary"] = ability_name

        growth_rate = growth_rates.get(int(row.get("growth_rate_id", 0)), "medium_fast")
        growth_rate = growth_rate.replace("-", "_")

        species_data = {
            "dex_number": dex_number,
            "name": species_names.get(species_id, row.get("identifier", "").title()),
            "types": types,
            "base_stats": base_stats,
            "abilities": abilities,
            "growth_rate": growth_rate,
            "catch_rate": int(row.get("capture_rate", 45)),
            "base_experience": int(default_row.get("base_experience", 0)),
            "height": int(default_row.get("height", 0)),
            "weight": int(default_row.get("weight", 0)),
            "gender_ratio": _gender_ratio(int(row.get("gender_rate", -1))),
            "description": flavor_texts.get(species_id, ""),
            "forms": [],
            "genus": species_genus.get(species_id, ""),
            "is_legendary": row.get("is_legendary") == "1",
            "is_mythical": row.get("is_mythical") == "1",
        }

        species_payload[str(dex_number)] = species_data

    return dict(sorted(species_payload.items(), key=lambda item: int(item[0])))


def main() -> None:
    species_payload = build_species_payload()
    OUTPUT_PATH.write_text(json.dumps(species_payload, indent=2, sort_keys=True))
    print(f"Wrote {len(species_payload)} species to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
