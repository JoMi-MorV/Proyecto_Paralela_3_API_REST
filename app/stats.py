"""
stats.py

Maneja el filtrado, validación y cálculo de estadísticas de ventas.

Las funciones de filtro implementan validaciones de valor específicas para cada
filtro admitido:
- GENERO: debe ser uno de los valores permitidos por GENERO_MAP.
- EDAD: debe ser entero y estar entre 10 y 120.
- CANAL: debe ser uno de los canales válidos en VALID_CANALES.
- CODIGO_PRODUCTO: debe ser un entero y corresponder a un producto existente.
- ID_PERSONA: debe ser UUID válido y corresponder a un cliente existente.
- LOCAL: debe ser entero y existir en los datos cargados.
- FECHA_DESDE / FECHA_HASTA: deben ser fechas ISO-8601 entre 1906-01-01 y hoy,
  y FECHA_DESDE no puede ser posterior a FECHA_HASTA.

También calcula métricas resumen y guarda caché de consultas GET precomputadas.
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

MIN_FILTER_DATE = pd.Timestamp("1906-01-01")


def _current_max_filter_date() -> pd.Timestamp:
    return pd.Timestamp.now().normalize()


def _validate_filter_date(value, name: str) -> pd.Timestamp:
    """Valida formato y rango para FECHA_DESDE / FECHA_HASTA."""
    try:
        fecha = pd.to_datetime(value)
    except (ValueError, TypeError):
        raise ValueError(f"El valor '{value}' no es una fecha ISO-8601 válida para {name}")

    if fecha.normalize() < MIN_FILTER_DATE:
        raise ValueError(
            f"El valor '{value}' no es válido para {name}; debe ser posterior o igual a {MIN_FILTER_DATE.date()}"
        )

    if fecha.normalize() > _current_max_filter_date():
        raise ValueError(
            f"El valor '{value}' no es válido para {name}; no puede ser posterior a hoy"
        )

    return fecha


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

    Cada filtro se valida antes de aplicarse. Si el valor no es válido se lanza
    ValueError con un mensaje legible. El controlador en main.py convierte
    ese ValueError en un error 400 Bad Request.
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

        if edad_buscada < 10 or edad_buscada > 120:
            raise ValueError(
                f"El valor '{valor}' no es válido para EDAD; debe estar entre 10 y 120"
            )

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

        if sku not in df["SKU"].values:
            raise ValueError(f"El valor '{valor}' no corresponde a un CODIGO_PRODUCTO existente")

        result = result[result["SKU"] == sku]

    if "ID_PERSONA" in filtros:
        valor = filtros["ID_PERSONA"]
        if not _is_valid_uuid(valor):
            raise ValueError(f"El valor '{valor}' no es un UUID válido para ID_PERSONA")

        if valor not in df["CODIGO CLIENTE"].values:
            raise ValueError(f"El valor '{valor}' no corresponde a un cliente existente")

        result = result[result["CODIGO CLIENTE"] == valor]

    if "LOCAL" in filtros:
        valor = filtros["LOCAL"]
        try:
            local = int(valor)
        except (ValueError, TypeError):
            raise ValueError(f"El valor '{valor}' no es un número entero válido para el ID de tienda")

        # Validar que el local exista en los datos antes de filtrar.
        if local not in result["LOCAL"].values:
            raise ValueError(f"El valor '{valor}' no corresponde a un LOCAL existente")

        result = result[result["LOCAL"] == local]

    fecha_desde = None
    if "FECHA_DESDE" in filtros:
        fecha_desde = _validate_filter_date(filtros["FECHA_DESDE"], "FECHA_DESDE")
        result = result[result["FECHA"] >= fecha_desde]

    if "FECHA_HASTA" in filtros:
        fecha_hasta = _validate_filter_date(filtros["FECHA_HASTA"], "FECHA_HASTA")
        if fecha_desde is not None and fecha_desde > fecha_hasta:
            raise ValueError("FECHA_DESDE no puede ser posterior a FECHA_HASTA")
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