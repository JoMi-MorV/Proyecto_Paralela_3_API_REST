"""
test_stats.py

Pruebas unitarias para la lógica de filtrado y estadísticas en app/stats.py.
Usa DataFrames pequeños construidos a mano en lugar del CSV real, por lo que
estas pruebas se ejecutan al instante y no dependen de que el archivo de datos exista.
"""

import pandas as pd
import pytest

from app.stats import apply_filters, compute_stats, validate_filter_keys, VALID_FILTERS


@pytest.fixture
def sample_df():
    """
    Conjunto de datos ficticio mínimo, reutilizado por cada función de prueba.
    pytest lo inyecta automáticamente en cualquier prueba que declare
    'sample_df' como parámetro.
    """
    return pd.DataFrame({
        "FECHA": pd.to_datetime([
            "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"
        ]),
        "CANAL": ["POS", "WEB", "POS", "APP"],
        "SKU": [100, 200, 100, 300],
        "PRODUCTO": ["A", "B", "A", "C"],
        "UNIDADES": [1, 2, 1, 3],
        "MONTO APLICADO": [1000.0, 2000.0, 1500.0, 500.0],
        "LOCAL": [1, 1, 2, 2],
        "CODIGO CLIENTE": [
            "7c44465b-9e50-3914-923f-9b4f6fbee508",
            "d8f9c1a2-4b3e-4c5d-9f6a-1b2c3d4e5f6a",
            "7c44465b-9e50-3914-923f-9b4f6fbee508",
            "a1b2c3d4-e5f6-4789-8abc-def012345678",
        ],
        "GÉNERO": [1, 2, 1, 2],
        "FECHA_NACIMIENTO": pd.to_datetime([
            "1990-01-01", "1995-06-15", "1990-01-01", "2000-03-20"
        ]),
    })


# ---------- pruebas de compute_stats() ----------

def test_compute_stats_basic_sum(sample_df):
    result = compute_stats(sample_df)
    # 1000 + 2000 + 1500 + 500 = 5000
    assert result["suma"] == 5000.0


def test_compute_stats_conteo(sample_df):
    result = compute_stats(sample_df)
    assert result["conteo"] == 4


def test_compute_stats_promedio(sample_df):
    result = compute_stats(sample_df)
    # 5000 / 4 = 1250
    assert result["promedio"] == 1250.0


def test_compute_stats_min_max(sample_df):
    result = compute_stats(sample_df)
    assert result["minimo"] == 500.0
    assert result["maximo"] == 2000.0


def test_compute_stats_mediana(sample_df):
    result = compute_stats(sample_df)
    # Valores: 500, 1000, 1500, 2000 -> mediana = (1000+1500)/2 = 1250
    assert result["mediana"] == 1250.0


def test_compute_stats_desviacion_estandar(sample_df):
    result = compute_stats(sample_df)
    assert result["desviacion_estandar"] > 0


def test_validate_filter_keys_rechaza_desconocidos():
    with pytest.raises(ValueError, match="no es un valor permitido"):
        validate_filter_keys({"FOO": "bar"})


def test_validate_filter_keys_acepta_validos():
    validate_filter_keys({"CANAL": "POS", "LOCAL": "1"})


def test_todos_los_filtros_estan_definidos():
    expected = {
        "GENERO", "EDAD", "CANAL", "CODIGO_PRODUCTO",
        "ID_PERSONA", "LOCAL", "FECHA_DESDE", "FECHA_HASTA",
    }
    assert VALID_FILTERS == expected


def test_compute_stats_empty_dataframe_returns_zeros():
    empty_df = pd.DataFrame({"MONTO APLICADO": []})
    result = compute_stats(empty_df)
    assert result["suma"] == 0
    assert result["conteo"] == 0
    assert result["promedio"] == 0


# ---------- pruebas de apply_filters() ----------

def test_filter_by_canal(sample_df):
    filtered = apply_filters(sample_df, {"CANAL": "POS"})
    assert len(filtered) == 2
    assert all(filtered["CANAL"] == "POS")


def test_filter_by_local(sample_df):
    filtered = apply_filters(sample_df, {"LOCAL": "1"})
    assert len(filtered) == 2
    assert all(filtered["LOCAL"] == 1)


def test_filter_by_codigo_producto(sample_df):
    filtered = apply_filters(sample_df, {"CODIGO_PRODUCTO": "100"})
    assert len(filtered) == 2
    assert all(filtered["SKU"] == 100)


def test_filter_by_genero_femenino(sample_df):
    filtered = apply_filters(sample_df, {"GENERO": "Femenino"})
    assert len(filtered) == 2
    assert all(filtered["GÉNERO"] == 2)


def test_filter_combined_canal_and_local(sample_df):
    filtered = apply_filters(sample_df, {"CANAL": "POS", "LOCAL": "1"})
    # Solo la fila 0 cumple CANAL=POS y LOCAL=1
    assert len(filtered) == 1


def test_filter_invalid_canal_raises_value_error(sample_df):
    with pytest.raises(ValueError):
        apply_filters(sample_df, {"CANAL": "NOT_A_REAL_CHANNEL"})


def test_filter_invalid_edad_raises_value_error(sample_df):
    with pytest.raises(ValueError):
        apply_filters(sample_df, {"EDAD": "not_a_number"})


def test_filter_by_id_persona(sample_df):
    filtered = apply_filters(sample_df, {"ID_PERSONA": "7c44465b-9e50-3914-923f-9b4f6fbee508"})
    assert len(filtered) == 2
    assert all(filtered["CODIGO CLIENTE"] == "7c44465b-9e50-3914-923f-9b4f6fbee508")


def test_filter_by_fecha_desde(sample_df):
    filtered = apply_filters(sample_df, {"FECHA_DESDE": "2026-01-03"})
    assert len(filtered) == 2


def test_filter_by_fecha_hasta(sample_df):
    filtered = apply_filters(sample_df, {"FECHA_HASTA": "2026-01-02"})
    assert len(filtered) == 2


def test_filter_invalid_local_raises_value_error(sample_df):
    with pytest.raises(ValueError, match="ID de tienda"):
        apply_filters(sample_df, {"LOCAL": "not_a_number"})


# ---------- integración: filtro + estadísticas ----------

def test_filter_then_compute_stats(sample_df):
    filtered = apply_filters(sample_df, {"CANAL": "POS"})
    result = compute_stats(filtered)
    # Filas POS: 1000.0 y 1500.0
    assert result["suma"] == 2500.0
    assert result["conteo"] == 2
    assert result["promedio"] == 1250.0
