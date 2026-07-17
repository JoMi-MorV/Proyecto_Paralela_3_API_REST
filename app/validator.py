"""
validator.py

Verifica que el DataFrame de ventas cargado tenga las columnas esperadas,
los tipos de datos correctos y que no existan filas estructuralmente rotas
antes de que la API comience a atender solicitudes. Se ejecuta una vez al
iniciar, inmediatamente después de load_data().
"""

import pandas as pd

# Columnas requeridas según la especificación del CSV del ejercicio,
# y la categoría de tipo de pandas a la que cada una debe pertenecer
# después de la carga.
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
    """Se lanza cuando el CSV cargado falla la validación estructural o de tipos."""
    pass


def validate_data(df: pd.DataFrame) -> dict:
    """
    Comprueba el DataFrame contra EXPECTED_COLUMNS para:
    - columnas faltantes
    - columnas extra inesperadas (solo advertencia, no fatal)
    - tipos de datos correctos por columna
    - comprobaciones básicas a nivel de fila (sin filas totalmente vacías,
      sin UNIDADES negativas, etc.)

    Devuelve un diccionario de reporte con advertencias. Lanza DataValidationError
    si los datos están lo suficientemente rotos como para que la API no pueda
    servir estadísticas correctas (por ejemplo, falta por completo una columna requerida).
    """
    report = {"errors": [], "warnings": [], "rows_checked": len(df)}

    # 1. Verificar que existe cada columna requerida
    missing = []
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            missing.append(col)
    if missing:
        report["errors"].append(f"Columnas faltantes: {missing}")

    # 2. Avisar sobre columnas extra inesperadas (no es fatal, solo se registra)
    extra = []
    for col in df.columns:
        if col not in EXPECTED_COLUMNS:
            extra.append(col)
    if extra:
        report["warnings"].append(f"Columnas no esperadas encontradas: {extra}")

    # Si faltan columnas requeridas, no podemos comprobar tipos/filas de forma segura —
    # detenerse aquí y lanzar inmediatamente.
    if report["errors"]:
        raise DataValidationError("; ".join(report["errors"]))

    # 3. Comprobaciones de tipo por columna
    for col, expected_type in EXPECTED_COLUMNS.items():
        series = df[col]

        if expected_type == "integer":
            invalid_mask = []
            for value in series:
                invalid_mask.append(not _is_valid_int(value))
            bad = series[invalid_mask]
            if len(bad) > 0:
                report["warnings"].append(
                    f"{len(bad)} valores no enteros en columna '{col}'"
                )

        elif expected_type == "float":
            invalid_mask = []
            for value in series:
                invalid_mask.append(not _is_valid_float(value))
            bad = series[invalid_mask]
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

    # 4. Comprobaciones de saneamiento a nivel de fila
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

    normalized_df = df.copy()
    for col in normalized_df.select_dtypes(include=["object"]).columns:
        normalized_df[col] = normalized_df[col].astype("string").str.strip()

    duplicate_rows = normalized_df.duplicated(keep="first").sum()
    if duplicate_rows > 0:
        report["warnings"].append(f"{duplicate_rows} filas duplicadas detectadas")

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