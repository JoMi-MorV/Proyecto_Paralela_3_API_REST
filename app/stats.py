"""
stats.py

Maneja el filtrado, cálculo y almacenamiento de estadísticas de ventas:
1. apply_filters()   -> filtra el DataFrame según criterios del usuario
2. compute_stats()   -> calcula el resumen estadístico requerido
3. StatsStore        -> precomputa métricas globales para GET y cachea consultas filtradas
"""

import uuid

import pandas as pd


# Mapea cada valor de GENERO listado en la especificación a su código numérico en el CSV.
# "No especificado" y "Otro" se incluyen explícitamente en lugar de
# tratarlos como "no coincidir con nada" — actualice estos dos códigos
# si su CSV real usa números distintos para ellos.
GENERO_MAP = {
    "No especificado": 0,
    "Masculino": 1,
    "Femenino": 2,
    "Otro": 3,
}

VALID_CANALES = {"POS", "WEB", "APP", "CCT", "APR", "WPR"}

VALID_FILTERS = {
    "GENERO",
    "EDAD",
    "CANAL",
    "CODIGO_PRODUCTO",
    "ID_PERSONA",
    "LOCAL",
    "FECHA_DESDE",
    "FECHA_HASTA",
}


def validate_filter_keys(filtros: dict) -> None:
    """Lanza ValueError si alguna clave de filtro no está en la especificación."""
    invalid = set(filtros.keys()) - VALID_FILTERS
    if invalid:
        nombre = "', '".join(sorted(invalid))
        raise ValueError(f"La consulta '{nombre}' no es un valor permitido")


def _is_valid_uuid(value) -> bool:
    """Valida que un valor tenga formato UUID canónico."""
    if pd.isna(value):
        return False

    text = str(value).strip()
    if not text:
        return False

    try:
        uuid.UUID(text)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def apply_filters(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """
    Aplica cero o más filtros al DataFrame de ventas.

    filtros: dict como {"GENERO": "Femenino", "CANAL": "POS"}
    Lanza ValueError con un mensaje legible si algún valor de filtro
    no es válido — el llamador (main.py) convierte esto en el
    formato de error 400 Bad Request requerido.
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

        # Cálculo correcto de la edad: resta 1 de la diferencia de años naiva
        # si el cumpleaños aún no ocurrió este año, en lugar de una aproximación
        # grosera con days // 365.
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
        if not _is_valid_uuid(valor):
            raise ValueError(f"El valor '{valor}' no es un UUID válido para ID_PERSONA")
        result = result[result["CODIGO CLIENTE"] == valor]

    if "LOCAL" in filtros:
        valor = filtros["LOCAL"]
        try:
            local = int(valor)
        except (ValueError, TypeError):
            raise ValueError(f"El valor '{valor}' no es un número entero válido para el ID de tienda")
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
    Calcula el resumen estadístico requerido:
    suma, conteo, promedio, mínimo, máximo, mediana, desviación estándar

    Devuelve estadísticas en cero si el DataFrame filtrado está vacío,
    en lugar de lanzar un error (resultados vacíos son válidos, solo poco interesantes).
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


class StatsStore:
    """
    Almacén de métricas precomputadas para el endpoint GET.

    Al iniciar la aplicación se calculan las estadísticas globales (sin filtros).
    Las consultas GET con filtros se resuelven desde una caché en memoria que se
    va poblando a medida que se solicitan combinaciones de filtros.
    """

    def __init__(self, df: pd.DataFrame):
        self._df = df
        self._global_stats = compute_stats(df)
        self._cache: dict[tuple, dict] = {}

    @property
    def global_stats(self) -> dict:
        return self._global_stats

    def get_precomputed(self, filtros: dict) -> dict:
        """Devuelve estadísticas precomputadas para los filtros indicados."""
        if not filtros:
            return self._global_stats

        key = tuple(sorted(filtros.items()))
        if key not in self._cache:
            filtered = apply_filters(self._df, filtros)
            self._cache[key] = compute_stats(filtered)

        return self._cache[key]