"""
validator.py

Verifies that the loaded sales DataFrame has the expected columns,
correct data types, and no structurally broken rows before the API
starts serving requests. Runs once at startup, right after load_data().
"""

import pandas as pd

# Columns required per the assignment's CSV spec, and the pandas dtype
# category each should belong to after loading.
EXPECTED_COLUMNS = {
    "FECHA": "datetime",
    "CANAL": "string",
    "SKU": "integer",
    "PRODUCTO": "string",
    "UNIDADES": "integer",
    "PORCENTAJE DESCUENTO": "float",
    "MONTO APLICADO": "float",
    "BOLETA": "integer",
    "LOCAL": "integer",
    "CODIGO CLIENTE": "string",
    "RUN CLIENTE": "string",
    "NOMBRES": "string",
    "APELLIDOS": "string",
    "FECHA_NACIMIENTO": "datetime",
    "GÉNERO": "integer",
}


class DataValidationError(Exception):
    """Raised when the loaded CSV fails structural or type validation."""
    pass


def validate_data(df: pd.DataFrame) -> dict:
    """
    Checks the DataFrame against EXPECTED_COLUMNS for:
    - missing columns
    - unexpected extra columns (warning only, not fatal)
    - correct data types per column
    - basic row-level sanity (no fully-empty rows, no negative UNIDADES, etc.)

    Returns a report dict with warnings. Raises DataValidationError if
    the data is broken badly enough that the API cannot serve correct
    statistics (e.g. a required column is missing entirely).
    """
    report = {"errors": [], "warnings": [], "rows_checked": len(df)}

    # 1. Check every required column exists
    missing = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    if missing:
        report["errors"].append(f"Columnas faltantes: {missing}")

    # 2. Warn about unexpected extra columns (not fatal, just noted)
    extra = [col for col in df.columns if col not in EXPECTED_COLUMNS]
    if extra:
        report["warnings"].append(f"Columnas no esperadas encontradas: {extra}")

    # If required columns are missing, we can't safely check types/rows —
    # stop here and raise immediately.
    if report["errors"]:
        raise DataValidationError("; ".join(report["errors"]))

    # 3. Type checks per column
    for col, expected_type in EXPECTED_COLUMNS.items():
        series = df[col]

        if expected_type == "integer":
            bad = series[~series.apply(_is_valid_int)]
            if len(bad) > 0:
                report["warnings"].append(
                    f"{len(bad)} valores no enteros en columna '{col}'"
                )

        elif expected_type == "float":
            bad = series[~series.apply(_is_valid_float)]
            if len(bad) > 0:
                report["warnings"].append(
                    f"{len(bad)} valores no numéricos en columna '{col}'"
                )

        elif expected_type == "datetime":
            bad = series.isna().sum()
            if bad > 0:
                report["warnings"].append(
                    f"{bad} fechas inválidas o no parseables en columna '{col}'"
                )

    # 4. Row-level sanity checks
    fully_empty_rows = df.isna().all(axis=1).sum()
    if fully_empty_rows > 0:
        report["warnings"].append(f"{fully_empty_rows} filas completamente vacías")

    if "UNIDADES" in df.columns:
        negative_units = (df["UNIDADES"] < 0).sum()
        if negative_units > 0:
            report["warnings"].append(f"{negative_units} filas con UNIDADES negativo")

    if "MONTO APLICADO" in df.columns:
        negative_amounts = (df["MONTO APLICADO"] < 0).sum()
        if negative_amounts > 0:
            report["warnings"].append(f"{negative_amounts} filas con MONTO APLICADO negativo")

    if "PORCENTAJE DESCUENTO" in df.columns:
        out_of_range = (
            (df["PORCENTAJE DESCUENTO"] < 0) | (df["PORCENTAJE DESCUENTO"] > 1)
        ).sum()
        if out_of_range > 0:
            report["warnings"].append(
                f"{out_of_range} filas con PORCENTAJE DESCUENTO fuera de rango (0-1)"
            )

    return report


def _is_valid_int(value) -> bool:
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def _is_valid_float(value) -> bool:
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False