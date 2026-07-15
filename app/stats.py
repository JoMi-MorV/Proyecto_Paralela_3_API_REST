"""
stats.py

Handles two responsibilities for the Cruz Morada sales statistics API:
1. apply_filters()  -> filters the sales DataFrame based on user-supplied criteria
2. compute_stats()  -> computes the required statistical summary on the filtered data

Both GET and POST endpoints in main.py call these same two functions,
so filter logic and calculation logic only exist in one place.
"""

from datetime import datetime
import pandas as pd


# Maps every GENERO value the spec lists to its numeric code in the CSV.
# "No especificado" and "Otro" are included explicitly rather than being
# treated as "match nothing" -- update these two codes if your real CSV
# uses different numbers for them.
GENERO_MAP = {
    "No especificado": 0,
    "Masculino": 1,
    "Femenino": 2,
    "Otro": 3,
}

VALID_CANALES = {"POS", "WEB", "APP", "CCT", "APR", "WPR"}


def apply_filters(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """
    Applies zero or more filters to the sales DataFrame.

    filtros: dict like {"GENERO": "Femenino", "CANAL": "POS"}
    Raises ValueError with a human-readable message if any filter
    value is invalid — the caller (main.py) converts this into the
    required 400 Bad Request error format.
    """
    result = df

    if "GENERO" in filtros:
        valor = filtros["GENERO"]
        if valor not in GENERO_MAP:
            raise ValueError(f"El valor '{valor}' no es válido para GENERO")
        result = result[result["GÉNERO"] == GENERO_MAP[valor]]

    if "EDAD" in filtros:
        valor = filtros["EDAD"]
        try:
            edad_buscada = int(valor)
        except (ValueError, TypeError):
            raise ValueError(f"El valor '{valor}' no es un número entero válido para EDAD")

        # Correct age calculation: subtracts 1 from the naive year
        # difference if the birthday hasn't occurred yet this year,
        # rather than a rough days // 365 approximation.
        hoy = pd.Timestamp.now()
        nacimiento = result["FECHA_NACIMIENTO"]

        edad_calculada = (hoy.year - nacimiento.dt.year) - (
            (hoy.month < nacimiento.dt.month)
            | ((hoy.month == nacimiento.dt.month) & (hoy.day < nacimiento.dt.day))
        )
        result = result[edad_calculada == edad_buscada]

    if "CANAL" in filtros:
        valor = filtros["CANAL"]
        if valor not in VALID_CANALES:
            raise ValueError(f"El valor '{valor}' no es válido para CANAL")
        result = result[result["CANAL"] == valor]

    if "CODIGO_PRODUCTO" in filtros:
        valor = filtros["CODIGO_PRODUCTO"]
        try:
            sku = int(valor)
        except (ValueError, TypeError):
            raise ValueError(f"El valor '{valor}' no es un número entero válido para CODIGO_PRODUCTO")
        result = result[result["SKU"] == sku]

    if "ID_PERSONA" in filtros:
        valor = filtros["ID_PERSONA"]
        result = result[result["CODIGO CLIENTE"] == valor]

    if "LOCAL" in filtros:
        valor = filtros["LOCAL"]
        try:
            local = int(valor)
        except (ValueError, TypeError):
            raise ValueError(f"El valor '{valor}' no es un número entero válido para LOCAL")
        result = result[result["LOCAL"] == local]

    if "FECHA_DESDE" in filtros:
        valor = filtros["FECHA_DESDE"]
        try:
            fecha_desde = pd.to_datetime(valor)
        except (ValueError, TypeError):
            raise ValueError(f"El valor '{valor}' no es una fecha ISO-8601 válida para FECHA_DESDE")
        result = result[result["FECHA"] >= fecha_desde]

    if "FECHA_HASTA" in filtros:
        valor = filtros["FECHA_HASTA"]
        try:
            fecha_hasta = pd.to_datetime(valor)
        except (ValueError, TypeError):
            raise ValueError(f"El valor '{valor}' no es una fecha ISO-8601 válida para FECHA_HASTA")
        result = result[result["FECHA"] <= fecha_hasta]

    return result


def compute_stats(df: pd.DataFrame, amount_column: str = "MONTO APLICADO") -> dict:
    """
    Computes the required statistical summary:
    suma, conteo, promedio, minimo, maximo, mediana, desviacion_estandar

    Returns all-zero stats if the filtered DataFrame is empty, rather
    than raising an error (empty results are valid, just uninteresting).
    """
    if len(df) == 0:
        return {
            "suma": 0,
            "conteo": 0,
            "promedio": 0,
            "minimo": 0,
            "maximo": 0,
            "mediana": 0,
            "desviacion_estandar": 0,
        }

    values = df[amount_column]

    return {
        "suma": round(float(values.sum()), 2),
        "conteo": int(values.count()),
        "promedio": round(float(values.mean()), 2),
        "minimo": round(float(values.min()), 2),
        "maximo": round(float(values.max()), 2),
        "mediana": round(float(values.median()), 2),
        "desviacion_estandar": round(float(values.std()), 2),
    }