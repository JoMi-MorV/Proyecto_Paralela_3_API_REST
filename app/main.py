"""
main.py

Cruz Morada - Estadísticas de Ventas API

Entry point for the FastAPI application. Loads and validates the sales
CSV once at startup (unattended, no manual step), then serves GET/POST
requests against /v1/estadisticas/ventas using the shared filtering
and statistics logic in stats.py, with validation from validator.py.
"""

import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.data_loader import load_data
from app.validator import validate_data, DataValidationError
from app.stats import apply_filters, compute_stats
from app.errors import build_error
from app.downloader import download_csv

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Cruz Morada - Estadísticas de Ventas API",
    description="Servicio REST para consultar estadísticas de ventas mediante GET y POST.",
    version="1.0.0",
    docs_url="/docs",
)

# Populated once at startup, then read (never modified) by every request.
sales_data = None


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect the base URL to the interactive API documentation."""
    return RedirectResponse(url="/docs", status_code=307)


@app.on_event("startup")
def startup_event():
    """
    Runs automatically when the server starts.
    1. Loads the CSV (streamed in chunks — see data_loader.py)
    2. Validates its structure/types (see validator.py)
    Satisfies the "unattended loading" requirement: no manual step
    is needed before the API is ready to serve requests.
    """
    
    
    
    global sales_data
    csv_path = download_csv()
    sales_data = load_data()

    try:
        report = validate_data(sales_data)
    except DataValidationError as e:
        # A required column is missing entirely — the API cannot
        # compute correct statistics, so fail fast and loud instead
        # of silently serving wrong numbers.
        logger.error(f"Validación de datos fallida: {e}")
        raise SystemExit(f"No se pudo iniciar la API: {e}")

    logger.info(f"Datos cargados y validados: {report['rows_checked']} filas")
    for warning in report["warnings"]:
        logger.warning(warning)


@app.get("/v1/estadisticas/ventas")
def get_estadisticas(
    request: Request,
    GENERO: str = None,
    EDAD: str = None,
    CANAL: str = None,
    CODIGO_PRODUCTO: str = None,
    ID_PERSONA: str = None,
    LOCAL: str = None,
    FECHA_DESDE: str = None,
    FECHA_HASTA: str = None,
):
    """
    Returns sales statistics filtered by optional query parameters.
    Example: /v1/estadisticas/ventas?CANAL=POS&GENERO=Femenino
    """
    filtros = {
        k: v
        for k, v in {
            "GENERO": GENERO,
            "EDAD": EDAD,
            "CANAL": CANAL,
            "CODIGO_PRODUCTO": CODIGO_PRODUCTO,
            "ID_PERSONA": ID_PERSONA,
            "LOCAL": LOCAL,
            "FECHA_DESDE": FECHA_DESDE,
            "FECHA_HASTA": FECHA_HASTA,
        }.items()
        if v is not None
    }

    try:
        filtered = apply_filters(sales_data, filtros)
        result = compute_stats(filtered)
        return result

    except ValueError as e:
        error = build_error(request, 400, str(e), "VF", "Validación Fallida")
        return JSONResponse(status_code=400, content=error)

    except Exception as e:
        logger.exception("Error inesperado calculando estadísticas (GET)")
        error = build_error(
            request, 500, f"Error al calcular estadísticas: {e}", "IE", "Error Interno"
        )
        return JSONResponse(status_code=500, content=error)


@app.post("/v1/estadisticas/ventas")
def post_estadisticas(request: Request, body: dict):
    """
    Returns sales statistics filtered by a JSON body of one or more
    "consultas". Example body:
    {
      "consultas": [
        {"consulta": "GENERO", "valor": "Femenino"},
        {"consulta": "CANAL", "valor": "POS"}
      ]
    }
    """
    consultas = body.get("consultas")

    if not consultas:
        error = build_error(
            request, 400, "consultas vacío o nulo", "VF", "Validación Fallida"
        )
        return JSONResponse(status_code=400, content=error)

    try:
        filtros = {c["consulta"]: c["valor"] for c in consultas}
    except (KeyError, TypeError):
        error = build_error(
            request,
            400,
            "Cada elemento de 'consultas' debe tener las claves 'consulta' y 'valor'",
            "VF",
            "Validación Fallida",
        )
        return JSONResponse(status_code=400, content=error)

    try:
        filtered = apply_filters(sales_data, filtros)
        result = compute_stats(filtered)
        return result

    except ValueError as e:
        error = build_error(request, 400, str(e), "VF", "Validación Fallida")
        return JSONResponse(status_code=400, content=error)

    except Exception as e:
        logger.exception("Error inesperado calculando estadísticas (POST)")
        error = build_error(
            request, 500, f"Error al calcular estadísticas: {e}", "IE", "Error Interno"
        )
        return JSONResponse(status_code=500, content=error)