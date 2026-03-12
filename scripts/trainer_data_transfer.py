#!/usr/bin/env python3
"""Utility to export/import trainer persistence files between environments.

Usage:
  python scripts/trainer_data_transfer.py export trainer_backup.zip
  python scripts/trainer_data_transfer.py import trainer_backup.zip
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

# Core trainer persistence files.
PERSISTENCE_FILES = [
    Path("data/players.db"),
    Path("config/player_inventory.json"),
    Path("config/rank_state.json"),
    Path("config/rank_matches.json"),
]


def export_backup(archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        included = 0
        for file_path in PERSISTENCE_FILES:
            if file_path.exists() and file_path.is_file():
                zf.write(file_path, arcname=str(file_path))
                included += 1
            else:
                print(f"[WARN] Missing file, skipping: {file_path}")

    size = archive_path.stat().st_size if archive_path.exists() else 0
    print(f"[OK] Backup created: {archive_path} ({size} bytes)")
    print(f"[OK] Files included: {included}/{len(PERSISTENCE_FILES)}")


def import_backup(archive_path: Path) -> None:
    if not archive_path.exists() or not archive_path.is_file():
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")

    with zipfile.ZipFile(archive_path, "r") as zf:
        names = set(zf.namelist())

        for file_path in PERSISTENCE_FILES:
            file_name = str(file_path)
            if file_name not in names:
                print(f"[WARN] Not present in archive, skipping: {file_name}")
                continue

            file_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(file_name) as src, open(file_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            print(f"[OK] Restored: {file_name}")

    print("[OK] Import complete.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export/import trainer data files (players DB + config cache/state)."
    )
    parser.add_argument("command", choices=["export", "import"], help="Operation to run")
    parser.add_argument("archive", help="Path to .zip archive to write/read")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    archive_path = Path(args.archive)

    if args.command == "export":
        export_backup(archive_path)
    else:
        import_backup(archive_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
