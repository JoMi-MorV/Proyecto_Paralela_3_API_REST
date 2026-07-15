"""
main.py

Cruz Morada - Estadísticas de Ventas API

Punto de entrada para la aplicación FastAPI. Carga y valida el CSV de ventas
una sola vez al iniciar (sin intervención manual), y luego atiende solicitudes
GET/POST en /v1/estadisticas/ventas usando la lógica compartida de filtrado
y estadísticas en stats.py, con validación provista por validator.py.
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

# Poblado una vez al iniciar, luego leído (nunca modificado) por cada solicitud.
sales_data = None


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect the base URL to the interactive API documentation."""
    return RedirectResponse(url="/docs", status_code=307)


@app.on_event("startup")
def startup_event():
    """
    Se ejecuta automáticamente cuando el servidor inicia.
    1. Carga el CSV (en streaming por chunks — ver data_loader.py)
    2. Valida su estructura/tipos (ver validator.py)
    Cumple el requisito de "carga desatendida": no se necesita ningún paso manual
    antes de que la API esté lista para atender solicitudes.
    """
    
    
    
    global sales_data
    csv_path = download_csv()
    sales_data = load_data(csv_path)

    try:
        report = validate_data(sales_data)
    except DataValidationError as e:
        # Falta por completo una columna obligatoria — la API no puede
        # calcular estadísticas correctas, por eso falla de forma rápida y visible
        # en vez de servir silenciosamente números incorrectos.
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
    Devuelve estadísticas de ventas filtradas por parámetros de consulta opcionales.
    Ejemplo: /v1/estadisticas/ventas?CANAL=POS&GENERO=Femenino
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
    Devuelve estadísticas de ventas filtradas por un cuerpo JSON con una o más
    "consultas". Ejemplo de cuerpo:
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