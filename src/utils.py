import csv
import json
import logging
from typing import Generator, Dict


def write_output_table_if_data(
        self,
        name: str,
        records: Generator[Dict, None, None],
        primary_key: list[str],
        incremental: bool
) -> bool:
    """
    Writes output CSV and manifest if records are present.
    Ensures all keys are included even if inconsistent across records.
    Nested objects are stringified as JSON.
    """
    records = list(records)  # Fully realize generator
    if not records:
        logging.info(f"No data found for '{name}'. Skipping output file.")
        return False

    # Build superset of all keys across all records
    all_keys = set()
    for record in records:
        all_keys.update(record.keys())

    all_keys = sorted(all_keys)  # Sort for consistency

    table_def = self.create_out_table_definition(
        f"{name}.csv",
        primary_key=primary_key,
        incremental=incremental
    )

    with open(table_def.full_path, mode="wt", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()

        for record in records:
            row = {}
            for key in all_keys:
                value = record.get(key)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                row[key] = value
            writer.writerow(row)

    logging.info(f"Dataset '{name}' downloaded. Writing manifest...")
    self.write_manifest(table_def)

    return True
