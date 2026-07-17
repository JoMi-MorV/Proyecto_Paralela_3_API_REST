"""
schemas.py

Modelos Pydantic usados por FastAPI para generar automáticamente la
documentación Swagger/OpenAPI y validar las solicitudes y respuestas del
servicio REST.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


FilterName = Literal[
    "GENERO",
    "EDAD",
    "CANAL",
    "CODIGO_PRODUCTO",
    "ID_PERSONA",
    "LOCAL",
    "FECHA_DESDE",
    "FECHA_HASTA",
]


class ConsultaItem(BaseModel):
    consulta: FilterName = Field(
        ...,
        description="Nombre del filtro a aplicar",
        examples=["GENERO"],
    )
    valor: str = Field(
        ...,
        description="Valor del filtro",
        examples=["Femenino"],
    )


class PostRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "consultas": [
                        {"consulta": "GENERO", "valor": "Femenino"},
                        {"consulta": "CANAL", "valor": "POS"},
                    ]
                }
            ]
        }
    )

    consultas: list[ConsultaItem] = Field(
        ...,
        description="Lista de filtros a aplicar sobre las ventas",
        min_length=1,
    )


class StatsResponse(BaseModel):
    suma: float = Field(..., examples=[1500.5])
    conteo: int = Field(..., examples=[42])
    promedio: float = Field(..., examples=[35.73])
    minimo: float = Field(..., examples=[10.0])
    maximo: float = Field(..., examples=[100.0])
    mediana: float = Field(..., examples=[30.0])
    desviacion_estandar: float = Field(..., examples=[25.4])


class ErrorResponse(BaseModel):
    detail: str
    instance: str
    status: int
    title: str
    type: str
    timestamp: str
    errorCode: str
    errorLabel: str
    method: str
