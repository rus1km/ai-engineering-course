"""
DVC Homework setup script.

Виконує весь pipeline:
  1. Ініціалізує git + DVC у dvc_workspace/
  2. Копіює брудний dataset і комітить як v1
  3. Очищає дані і комітить як v2

Використання:
    python setup_workspace.py
"""

import csv
import shutil
import subprocess
import sys
from pathlib import Path


SRC_CSV = Path("data/dataset_v1.csv")
WORKSPACE = Path("dvc_workspace")
DATASET = WORKSPACE / "dataset.csv"


def run(cmd: str, cwd: Path = WORKSPACE) -> None:
    result = subprocess.run(cmd, shell=True, cwd=str(cwd), text=True,
                            capture_output=True)
    if result.returncode != 0:
        print(f"ERROR running: {cmd}")
        print(result.stderr.strip())
        sys.exit(1)
    if result.stdout.strip():
        print(result.stdout.strip())


def clean_csv(src: Path, dst: Path) -> None:
    with src.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    seen_ids = set()
    cleaned = []
    for row in rows:
        # Видаляємо дублікати (за id)
        if row["id"] in seen_ids:
            continue
        seen_ids.add(row["id"])

        # Видаляємо рядки з пропущеними значеннями
        if any(v.strip() == "" for v in row.values()):
            continue

        # Lowercase для category
        row["category"] = row["category"].strip().lower()

        # Фіксуємо Bob: category має бути enterprise
        if row["name"] == "Bob":
            row["category"] = "enterprise"

        # Фіксуємо Hank: value має бути 4800
        if row["name"] == "Hank":
            row["value"] = "4800"

        cleaned.append(row)

    with dst.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned)

    print(f"Cleaned: {len(cleaned)} rows written to {dst}")


def main() -> None:
    # Якщо workspace вже існує — очищаємо
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)

    WORKSPACE.mkdir()

    # --- Init git + DVC ---
    print("\n--- Initializing git + DVC ---")
    run("git init", cwd=WORKSPACE)
    run("git config user.email 'student@example.com'", cwd=WORKSPACE)
    run("git config user.name 'Student'", cwd=WORKSPACE)
    run("dvc init", cwd=WORKSPACE)
    run("git add .dvc .dvcignore", cwd=WORKSPACE)
    run("git commit -m 'Initialize DVC'", cwd=WORKSPACE)

    # --- V1: брудні дані ---
    print("\n--- Committing v1 (dirty data) ---")
    shutil.copy(SRC_CSV, DATASET)
    run("dvc add dataset.csv", cwd=WORKSPACE)
    run("git add dataset.csv.dvc .gitignore", cwd=WORKSPACE)
    run("git commit -m 'Add dataset v1 (dirty data)'", cwd=WORKSPACE)

    # --- V2: чисті дані ---
    print("\n--- Committing v2 (clean data) ---")
    clean_csv(SRC_CSV, DATASET)
    run("dvc add dataset.csv", cwd=WORKSPACE)
    run("git add dataset.csv.dvc", cwd=WORKSPACE)
    run("git commit -m 'Clean dataset v2'", cwd=WORKSPACE)

    print("\nDone! Run: python evaluate.py")


if __name__ == "__main__":
    main()
