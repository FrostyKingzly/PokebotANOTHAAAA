"""
Generate a comprehensive evolution_data.json using PokeAPI's CSV dumps.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List
from urllib.request import urlopen

DATA_DIR = Path(__file__).resolve().parents[1] / "pokeapi_csv_bot"
BASE_URL = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
CSV_FILES = {
    "pokemon_species": "pokemon_species.csv",
    "pokemon_evolution": "pokemon_evolution.csv",
    "evolution_triggers": "evolution_triggers.csv",
    "items": "items.csv",
    "moves": "moves.csv",
    "types": "types.csv",
}


def fetch_csv(name: str) -> List[Dict[str, str]]:
    csv_name = CSV_FILES[name]
    local_path = DATA_DIR / csv_name

    if local_path.exists():
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read().splitlines()
        return list(csv.DictReader(content))

    url = BASE_URL + csv_name
    with urlopen(url) as resp:
        content = resp.read().decode("utf-8")
    return list(csv.DictReader(content.splitlines()))


def normalize(identifier: str) -> str:
    return identifier.replace("-", "_") if identifier else identifier


def build_evolution_data() -> Dict[str, dict]:
    species_rows = fetch_csv("pokemon_species")
    evo_rows = fetch_csv("pokemon_evolution")
    trigger_rows = fetch_csv("evolution_triggers")
    item_rows = fetch_csv("items")
    move_rows = fetch_csv("moves")
    type_rows = fetch_csv("types")

    species_by_id = {int(row["id"]): row for row in species_rows}
    species_name = {sid: row["identifier"] for sid, row in species_by_id.items()}

    trigger_lookup = {int(r["id"]): r["identifier"] for r in trigger_rows}
    item_lookup = {int(r["id"]): normalize(r["identifier"]) for r in item_rows}
    move_lookup = {int(r["id"]): normalize(r["identifier"]) for r in move_rows}
    type_lookup = {int(r["id"]): r["identifier"] for r in type_rows}

    evolutions: Dict[str, dict] = {normalize(row["identifier"]): {"method": "none"} for row in species_rows}
    pending: Dict[str, List[dict]] = defaultdict(list)

    for row in evo_rows:
        target_id = int(row["evolved_species_id"])
        target_species = species_by_id.get(target_id)
        if not target_species:
            continue
        base_id = target_species.get("evolves_from_species_id")
        if not base_id:
            continue
        base_id = int(base_id)
        base_name = normalize(species_name.get(base_id, ""))
        target_name = normalize(species_name.get(target_id, ""))

        trigger = trigger_lookup.get(int(row["evolution_trigger_id"]))
        if not trigger:
            continue

        option = {"into": target_name}
        trigger_item = row.get("trigger_item_id")
        min_level = row.get("minimum_level")
        min_happiness = row.get("minimum_happiness")
        min_affection = row.get("minimum_affection")
        min_beauty = row.get("minimum_beauty")
        known_move = row.get("known_move_id")
        known_move_type = row.get("known_move_type_id")
        trade_species = row.get("trade_species_id")
        time_of_day = row.get("time_of_day")

        if trigger == "use-item":
            option["method"] = "stone"
            if trigger_item:
                option["stone"] = item_lookup.get(int(trigger_item))
        elif trigger == "trade":
            option["method"] = "trade"
            if trigger_item:
                option["item"] = item_lookup.get(int(trigger_item))
            if trade_species:
                option["trade_species"] = normalize(species_name.get(int(trade_species), ""))
        elif trigger == "level-up":
            if (min_happiness and min_happiness != "") or (min_affection and min_affection != ""):
                option["method"] = "friendship"
            elif min_beauty and min_beauty != "":
                option["method"] = "friendship"
            else:
                option["method"] = "level"
            if min_level:
                option["level"] = int(min_level)
            if known_move:
                option["move"] = move_lookup.get(int(known_move))
            if known_move_type:
                option["move_type"] = type_lookup.get(int(known_move_type))
            if time_of_day:
                option["time"] = time_of_day
        else:
            option["method"] = trigger

        pending[base_name].append(option)

    for base_name, options in pending.items():
        if not options:
            continue
        if len(options) == 1:
            evolutions[base_name] = options[0]
        else:
            evolutions[base_name] = {"method": "multiple", "evolutions": options}

    return dict(sorted(evolutions.items()))


def main() -> None:
    data = build_evolution_data()
    out_path = Path(__file__).resolve().parents[1] / "data" / "evolution_data.json"
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True))
    print(f"Wrote {len(data)} entries to {out_path}")


if __name__ == "__main__":
    main()
