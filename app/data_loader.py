"""
data_loader.py

Carga el CSV de ventas de Cruz Morada en la memoria al iniciar la aplicación.

IMPORTANTE: este CSV utiliza un formato de doble codificación no estándar.
El delimitador real es ';', con los campos individuales envueltos en comillas dobles
(""valor""). Debido a que al menos un valor de PRODUCTO contiene una coma literal no
escapada, el archivo se corrompió al guardarse/exportarse originalmente como un CSV
delimitado por comas; cada fila se dividió/entrecomilló incorrectamente en esa coma
y se añadieron dos comas residuales al final de cada línea.

reconstruct_row() revierte esto: vuelve a unir las piezas divididas incorrectamente
(restaurando la coma que pertenece al interior de los datos reales), luego divide
según el delimitador real ';' y elimina los caracteres de comillas sobrantes.

Dado que el archivo tiene más de 3 millones de filas, este trabajo de reconstrucción
se distribuye en un grupo de hilos (hasta NUM_THREADS trabajadores) en lugar de
procesarse fila por fila en un solo bucle, conforme al requisito de procesamiento
en paralelo de la tarea. No se escribe ninguna copia limpia o modificada del CSV
en el disco; todo sucede en la memoria antes de ser cargado en un único DataFrame,
ya que escribir un segundo archivo de 3 millones de filas solo añadiría un tiempo de E/S innecesario.
"""

import csv
import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

logger = logging.getLogger("uvicorn.error")

CSV_PATH = "data/ventas_completas.csv"
NUM_THREADS = 32
CHUNK_SIZE = 50_000  # rows handed to each thread per batch


# Orden de las columnas tal y como aparecen realmente en el archivo 
# original (después de restaurar el delimitador ';' real).
RAW_COLUMNS = [
    "FECHA", "CANAL", "SKU", "PRODUCTO", "UNIDADES",
    "PORCENTAJE DESCUENTO", "MONTO APLICADO", "BOLETA", "LOCAL",
    "CODIGO CLIENTE", "RUN CLIENTE", "NOMBRES", "APELLIDOS",
    "FECHA NACIMIENTO", "GENERO",
]


# Cambia el nombre de un par de columnas originales a los nombres
# canónicos que ya se utilizan en todo validator.py / stats.py,
# para que esos archivos no necesiten ser modificados.
RENAME_MAP = {
    "FECHA NACIMIENTO": "FECHA_NACIMIENTO",
    "GENERO": "GÉNERO",
}

NUMERIC_INT_COLUMNS = ["SKU", "UNIDADES", "BOLETA", "LOCAL", "GÉNERO"]
NUMERIC_FLOAT_COLUMNS = ["PORCENTAJE DESCUENTO", "MONTO APLICADO"]


def _reconstruct_row(outer_row: list) -> list | None:
    """
    Invierte la doble codificación de una sola fila.
    Devuelve None si la fila está vacía o no es utilizable después de la limpieza.
    """
    # Elimina los campos vacíos residuales al final (provenientes de las comas extra ',,' por línea).
    while outer_row and outer_row[-1] == "":
        outer_row.pop()

    if not outer_row:
        return None

    # Vuelve a unir con ',' para restaurar cualquier coma que pertenezca al interior de los datos
    # (esto deshace la división externa incorrecta causada por la coma en PRODUCTO)
    joined = ",".join(outer_row)

    # Ahora divide usando el delimitador REAL y elimina los caracteres de comillas sobrantes
    fields = [f.strip().strip('"') for f in joined.split(";")]
    return fields


def _reconstruct_chunk(rows: list) -> list:
    """
    Reconstruye un lote de filas crudas. Esta es la función que ejecuta cada hilo
    — trabajo ligero de cadenas de caracteres, dividido entre los trabajadores NUM_THREADS.
    Las filas que no se reconstruyen al recuento de columnas esperado son
    eliminadas (registradas como omitidas por el llamador) en lugar de corromper
    el DataFrame con columnas desalineadas.
    """
    result = []
    for row in rows:
        fields = _reconstruct_row(row)
        if fields is not None and len(fields) == len(RAW_COLUMNS):
            result.append(fields)
    return result


def load_data(csv_path: str = CSV_PATH) -> pd.DataFrame:
    """
    Lee el CSV original, reconstruye la verdadera estructura de campos de cada
    fila en paralelo utilizando un grupo de hilos, y devuelve un DataFrame limpio.
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=",", quotechar='"')
        next(reader)  # ignora la fila de encabezado original (que también tiene doble codificación)
        raw_rows = list(reader)

    total_rows = len(raw_rows)
    logger.info(
        f"Archivo leído: {total_rows} filas crudas. "
        f"Reconstruyendo en paralelo con {NUM_THREADS} hilos..."
    )

    # Divide las filas originales en lotes, enviando un lote por cada tarea de hilo.
    batches = [
        raw_rows[i:i + CHUNK_SIZE]
        for i in range(0, total_rows, CHUNK_SIZE)
    ]

    reconstructed_rows = []
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = [executor.submit(_reconstruct_chunk, batch) for batch in batches]
        for future in futures:
            reconstructed_rows.extend(future.result())

    skipped = total_rows - len(reconstructed_rows)
    if skipped > 0:
        logger.warning(f"{skipped} filas omitidas por formato inválido tras la reconstrucción")

    df = pd.DataFrame(reconstructed_rows, columns=RAW_COLUMNS)
    df = df.rename(columns=RENAME_MAP)

    # Conversiones de tipo: errors="coerce" convierte los valores individuales
    # que no se pueden analizar en NaT/NaN en lugar de hacer que toda la carga falle;
    # estos son detectados posteriormente como advertencias por validate_data().
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df["FECHA_NACIMIENTO"] = pd.to_datetime(df["FECHA_NACIMIENTO"], errors="coerce")

    for col in NUMERIC_INT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in NUMERIC_FLOAT_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"Carga completa: {len(df)} filas cargadas desde '{csv_path}'")
    return df