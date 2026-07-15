"""
data_loader.py

Loads the Cruz Morada sales CSV into memory at application startup.

IMPORTANT: this CSV uses a nonstandard double-encoded format. The true
delimiter is ';', with individual fields wrapped in doubled quotes
(""value""). Because at least one PRODUCTO value contains a literal,
unescaped comma, the file was corrupted when originally saved/exported
as comma-delimited CSV -- every row was incorrectly split/quoted at
that comma, and two stray trailing commas were appended per line.

reconstruct_row() reverses this: it re-joins the incorrectly-split
outer pieces (restoring the comma that belongs inside the real data),
then splits on the *real* delimiter ';' and strips the leftover quote
characters.

Given the file has 3M+ rows, this reconstruction work is spread across
a thread pool (up to NUM_THREADS workers) rather than processed
row-by-row in a single loop, per the assignment's parallel-processing
requirement. No cleaned/modified copy of the CSV is written to disk --
everything happens in memory before being loaded into one DataFrame,
since writing a second 3M-row file would just add unnecessary I/O time.
"""

import csv
import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

logger = logging.getLogger("uvicorn.error")

CSV_PATH = "data/ventas_completas.csv"
NUM_THREADS = 32
CHUNK_SIZE = 50_000  # rows handed to each thread per batch

# Column order as they actually appear in the raw file (after the real
# ';' delimiter is restored).
RAW_COLUMNS = [
    "FECHA", "CANAL", "SKU", "PRODUCTO", "UNIDADES",
    "PORCENTAJE DESCUENTO", "MONTO APLICADO", "BOLETA", "LOCAL",
    "CODIGO CLIENTE", "RUN CLIENTE", "NOMBRES", "APELLIDOS",
    "FECHA NACIMIENTO", "GENERO",
]

# Renames a couple of raw column names to the canonical names already
# used throughout validator.py / stats.py, so those files don't need
# to change.
RENAME_MAP = {
    "FECHA NACIMIENTO": "FECHA_NACIMIENTO",
    "GENERO": "GÉNERO",
}

NUMERIC_INT_COLUMNS = ["SKU", "UNIDADES", "BOLETA", "LOCAL", "GÉNERO"]
NUMERIC_FLOAT_COLUMNS = ["PORCENTAJE DESCUENTO", "MONTO APLICADO"]


def _reconstruct_row(outer_row: list) -> list | None:
    """
    Reverses the double-encoding for a single row.
    Returns None if the row is empty/unusable after cleanup.
    """
    # Drop the stray empty trailing fields (from the extra ',,' per line)
    while outer_row and outer_row[-1] == "":
        outer_row.pop()

    if not outer_row:
        return None

    # Re-join with ',' to restore any comma that belongs inside the data
    # (this undoes the incorrect outer split caused by the PRODUCTO comma)
    joined = ",".join(outer_row)

    # Now split on the REAL delimiter and strip leftover quote characters
    fields = [f.strip().strip('"') for f in joined.split(";")]
    return fields


def _reconstruct_chunk(rows: list) -> list:
    """
    Reconstructs a batch of raw rows. This is the function each thread
    runs — CPU-light string work, split across NUM_THREADS workers.
    Rows that don't reconstruct to the expected column count are
    dropped (logged as skipped by the caller) rather than corrupting
    the DataFrame with misaligned columns.
    """
    result = []
    for row in rows:
        fields = _reconstruct_row(row)
        if fields is not None and len(fields) == len(RAW_COLUMNS):
            result.append(fields)
    return result


def load_data(csv_path: str = CSV_PATH) -> pd.DataFrame:
    """
    Reads the raw CSV, reconstructs every row's true field structure
    in parallel using a thread pool, and returns a clean DataFrame.
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=",", quotechar='"')
        next(reader)  # skip the raw (also double-encoded) header row
        raw_rows = list(reader)

    total_rows = len(raw_rows)
    logger.info(
        f"Archivo leído: {total_rows} filas crudas. "
        f"Reconstruyendo en paralelo con {NUM_THREADS} hilos..."
    )

    # Split the raw rows into batches, one batch submitted per thread task
    batches = [
        raw_rows[i:i + CHUNK_SIZE]
        for i in range(0, total_rows, CHUNK_SIZE)
    ]

    reconstructed_rows = []
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = [executor.submit(_reconstruct_chunk, batch) for batch in batches]
        for future in futures:
            reconstructed_rows.extend(future.result())

    skipped = total_rows - len(reconstructed_rows)
    if skipped > 0:
        logger.warning(f"{skipped} filas omitidas por formato inválido tras la reconstrucción")

    df = pd.DataFrame(reconstructed_rows, columns=RAW_COLUMNS)
    df = df.rename(columns=RENAME_MAP)

    # Type conversions -- errors="coerce" turns unparseable individual
    # values into NaT/NaN instead of crashing the whole load; those get
    # caught as warnings by validate_data() afterward.
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df["FECHA_NACIMIENTO"] = pd.to_datetime(df["FECHA_NACIMIENTO"], errors="coerce")

    for col in NUMERIC_INT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in NUMERIC_FLOAT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"Carga completa: {len(df)} filas cargadas desde '{csv_path}'")
    return df