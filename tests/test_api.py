"""
test_api.py

Pruebas de integración para los endpoints GET y POST usando TestClient.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.stats import StatsStore


@pytest.fixture
def sample_df():
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


@pytest.fixture
def client(sample_df, monkeypatch):
    def fake_download_csv():
        return "fake.csv"

    def fake_load_data(path):
        return sample_df

    def fake_validate_data(df):
        return {"rows_checked": len(df), "warnings": []}

    monkeypatch.setattr("app.main.download_csv", fake_download_csv)
    monkeypatch.setattr("app.main.load_data", fake_load_data)
    monkeypatch.setattr("app.main.validate_data", fake_validate_data)

    with TestClient(app) as test_client:
        yield test_client


def test_get_sin_filtros_usa_metricas_precomputadas(client):
    response = client.get("/v1/estadisticas/ventas")
    assert response.status_code == 200
    data = response.json()
    assert data["suma"] == 5000.0
    assert data["conteo"] == 4


def test_get_con_filtro_canal(client):
    response = client.get("/v1/estadisticas/ventas?CANAL=POS")
    assert response.status_code == 200
    data = response.json()
    assert data["suma"] == 2500.0
    assert data["conteo"] == 2


def test_get_consulta_invalida_retorna_400(client):
    response = client.get("/v1/estadisticas/ventas?FOO=bar")
    assert response.status_code == 400
    data = response.json()
    assert data["errorCode"] == "VF"
    assert data["errorLabel"] == "Validación Fallida"
    assert data["status"] == 400
    assert data["instance"] == "/v1/estadisticas/ventas"
    assert data["method"] == "GET"
    assert "FOO" in data["detail"]
    assert data["timestamp"].endswith("Z")


def test_get_valor_invalido_retorna_400(client):
    response = client.get("/v1/estadisticas/ventas?CANAL=INVALIDO")
    assert response.status_code == 400
    assert "CANAL" in response.json()["detail"]


def test_post_filtros_validos(client):
    response = client.post(
        "/v1/estadisticas/ventas",
        json={
            "consultas": [
                {"consulta": "CANAL", "valor": "POS"},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["suma"] == 2500.0
    assert data["conteo"] == 2


def test_post_consultas_vacio_retorna_400(client):
    response = client.post("/v1/estadisticas/ventas", json={"consultas": []})
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "consultas vacío o nulo"
    assert data["errorCode"] == "VF"


def test_post_consulta_invalida_retorna_400(client):
    response = client.post(
        "/v1/estadisticas/ventas",
        json={"consultas": [{"consulta": "FOO", "valor": "x"}]},
    )
    assert response.status_code == 400
    data = response.json()
    assert "FOO" in data["detail"]
    assert data["errorCode"] == "VF"


def test_post_sin_clave_consultas_retorna_400(client):
    response = client.post("/v1/estadisticas/ventas", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "consultas vacío o nulo"


def test_post_elemento_sin_valor_retorna_400(client):
    response = client.post(
        "/v1/estadisticas/ventas",
        json={"consultas": [{"consulta": "CANAL"}]},
    )
    assert response.status_code == 400
    assert "consulta" in response.json()["detail"]


def test_respuesta_exitosa_tiene_todas_las_metricas(client):
    response = client.get("/v1/estadisticas/ventas")
    data = response.json()
    for key in (
        "suma", "conteo", "promedio", "minimo",
        "maximo", "mediana", "desviacion_estandar",
    ):
        assert key in data


def test_stats_store_precalcula_globales(sample_df):
    store = StatsStore(sample_df)
    assert store.global_stats["suma"] == 5000.0
    assert store.get_precomputed({}) == store.global_stats


def test_stats_store_cachea_filtros(sample_df):
    store = StatsStore(sample_df)
    filtros = {"CANAL": "POS"}
    first = store.get_precomputed(filtros)
    second = store.get_precomputed(filtros)
    assert first is second
    assert first["conteo"] == 2
