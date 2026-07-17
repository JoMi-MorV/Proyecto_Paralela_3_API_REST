"""
main.py

Cruz Morada - Estadísticas de Ventas API

Punto de entrada para la aplicación FastAPI. Carga y valida el CSV de ventas
una sola vez al iniciar (sin intervención manual), precomputa métricas globales
para GET, y atiende consultas dinámicas vía POST.
"""

import logging
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from app.data_loader import load_data
from app.downloader import download_csv
from app.errors import build_error
from app.schemas import ErrorResponse, PostRequest, StatsResponse
from app.stats import (
    VALID_FILTERS,
    StatsStore,
    apply_filters,
    compute_stats,
    validate_filter_keys,
)
from app.validator import DataValidationError, validate_data

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Cruz Morada - Estadísticas de Ventas API",
    description=(
        "Servicio REST para consultar estadísticas de ventas de Cruz Morada.\n\n"
        "- **GET**: devuelve métricas precomputadas al iniciar la aplicación, "
        "con filtros opcionales vía query params.\n"
        "- **POST**: realiza consultas dinámicas con filtros personalizados en el body JSON."
    ),
    version="1.0.0",
    docs_url="/docs",
)

sales_data = None
stats_store: StatsStore | None = None

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Validación fallida"},
    500: {"model": ErrorResponse, "description": "Error interno"},
}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    detail = "Validación Fallida"

    for err in exc.errors():
        loc = err.get("loc", ())
        err_type = err.get("type")

        if loc == ("body", "consultas") and err_type in {"too_short", "missing"}:
            detail = "consultas vacío o nulo"
            break

        if loc == ("body",) and err_type == "missing":
            detail = "consultas vacío o nulo"
            break

        if "consulta" in loc and err_type == "literal_error":
            detail = f"La consulta '{err.get('input')}' no es un valor permitido"
            break

        if loc[:2] == ("body", "consultas") and err_type == "missing":
            detail = "Cada elemento de 'consultas' debe tener las claves 'consulta' y 'valor'"
            break

    error = build_error(request, 400, detail, "VF", "Validación Fallida")
    return JSONResponse(status_code=400, content=error)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirige la URL base a la documentación interactiva."""
    return RedirectResponse(url="/docs", status_code=307)


@app.on_event("startup")
def startup_event():
    """
    Se ejecuta automáticamente cuando el servidor inicia.
    1. Descarga/carga el CSV (ver downloader.py y data_loader.py)
    2. Valida su estructura/tipos (ver validator.py)
    3. Precomputa métricas globales para consultas GET
    """
    global sales_data, stats_store

    csv_path = download_csv()
    sales_data = load_data(csv_path)

    try:
        report = validate_data(sales_data)
    except DataValidationError as e:
        logger.error(f"Validación de datos fallida: {e}")
        raise SystemExit(f"No se pudo iniciar la API: {e}")

    stats_store = StatsStore(sales_data)
    logger.info(f"Datos cargados y validados: {report['rows_checked']} filas")
    logger.info("Métricas globales precomputadas para consultas GET")
    for warning in report["warnings"]:
        logger.warning(warning)


def _unknown_query_params(request: Request) -> set[str]:
    return set(request.query_params.keys()) - VALID_FILTERS


def _build_filtros_from_query(
    genero: str | None,
    edad: str | None,
    canal: str | None,
    codigo_producto: str | None,
    id_persona: str | None,
    local: str | None,
    fecha_desde: str | None,
    fecha_hasta: str | None,
) -> dict:
    filtros = {}
    filter_values = {
        "GENERO": genero,
        "EDAD": edad,
        "CANAL": canal,
        "CODIGO_PRODUCTO": codigo_producto,
        "ID_PERSONA": id_persona,
        "LOCAL": local,
        "FECHA_DESDE": fecha_desde,
        "FECHA_HASTA": fecha_hasta,
    }

    for key, value in filter_values.items():
        if value is not None:
            filtros[key] = value

    return filtros


@app.get(
    "/v1/estadisticas/ventas",
    response_model=StatsResponse,
    responses=ERROR_RESPONSES,
    summary="Consultar métricas precomputadas",
    description=(
        "Devuelve estadísticas de ventas usando métricas precomputadas al iniciar "
        "la aplicación. Acepta filtros opcionales como query params.\n\n"
        "**Ejemplo:** `/v1/estadisticas/ventas?CANAL=POS&GENERO=Femenino`"
    ),
)
def get_estadisticas(
    request: Request,
    GENERO: Annotated[str | None, Query(description="Género del cliente")] = None,
    EDAD: Annotated[str | None, Query(description="Edad en años")] = None,
    CANAL: Annotated[str | None, Query(description="Canal de venta")] = None,
    CODIGO_PRODUCTO: Annotated[str | None, Query(description="SKU del producto")] = None,
    ID_PERSONA: Annotated[str | None, Query(description="UUID del cliente")] = None,
    LOCAL: Annotated[str | None, Query(description="Número de local")] = None,
    FECHA_DESDE: Annotated[str | None, Query(description="Fecha mínima ISO-8601")] = None,
    FECHA_HASTA: Annotated[str | None, Query(description="Fecha máxima ISO-8601")] = None,
):
    unknown = _unknown_query_params(request)
    if unknown:
        nombre = "', '".join(sorted(unknown))
        error = build_error(
            request,
            400,
            f"La consulta '{nombre}' no es un valor permitido",
            "VF",
            "Validación Fallida",
        )
        return JSONResponse(status_code=400, content=error)

    filtros = _build_filtros_from_query(
        GENERO, EDAD, CANAL, CODIGO_PRODUCTO, ID_PERSONA, LOCAL, FECHA_DESDE, FECHA_HASTA
    )

    try:
        validate_filter_keys(filtros)
        return stats_store.get_precomputed(filtros)

    except ValueError as e:
        error = build_error(request, 400, str(e), "VF", "Validación Fallida")
        return JSONResponse(status_code=400, content=error)

    except Exception:
        logger.exception("Error inesperado calculando estadísticas (GET)")
        error = build_error(
            request, 500, "Error al calcular la desviación estándar", "IE", "Error Interno"
        )
        return JSONResponse(status_code=500, content=error)


@app.post(
    "/v1/estadisticas/ventas",
    response_model=StatsResponse,
    responses=ERROR_RESPONSES,
    summary="Consulta dinámica con filtros",
    description=(
        "Realiza una consulta dinámica aplicando uno o más filtros en el body JSON.\n\n"
        '**Ejemplo de body:** `{"consultas": [{"consulta": "GENERO", "valor": "Femenino"}]}`'
    ),
)
def post_estadisticas(request: Request, body: PostRequest):
    try:
        filtros = {}
        for consulta in body.consultas:
            filtros[consulta.consulta] = consulta.valor
        validate_filter_keys(filtros)
        filtered = apply_filters(sales_data, filtros)
        return compute_stats(filtered)

    except ValueError as e:
        error = build_error(request, 400, str(e), "VF", "Validación Fallida")
        return JSONResponse(status_code=400, content=error)

    except Exception:
        logger.exception("Error inesperado calculando estadísticas (POST)")
        error = build_error(
            request, 500, "Error al calcular la desviación estándar", "IE", "Error Interno"
        )
        return JSONResponse(status_code=500, content=error)
