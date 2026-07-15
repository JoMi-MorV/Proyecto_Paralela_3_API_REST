"""
downloader.py

Descarga automáticamente el CSV de ventas desde Google Drive al iniciar, por
lo que no se requiere ningún paso de descarga manual (cumple con el requisito
de "carga desatendida"; el archivo ni siquiera necesita estar presente en el disco de antemano).
"""

import logging
from pathlib import Path

import gdown

logger = logging.getLogger("uvicorn.error")

# Extracted from the share link:
# https://drive.google.com/file/d/15jLBlJ9eMQSoHsoCMnFWBGopr98FIHlK/view?usp=sharing
GOOGLE_DRIVE_FILE_ID = "15jLBlJ9eMQSoHsoCMnFWBGopr98FIHlK"

DEST_PATH = "data/ventas_completas.csv"


def download_csv(dest_path: str = DEST_PATH, force: bool = False) -> str:
    """
    Descarga el CSV desde Google Drive si no está presente localmente.
    Establece force=True para volver a descargarlo siempre (por ejemplo,
    si el archivo de origen se actualiza entre ejecuciones).
    """
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not force:
        logger.info(f"CSV ya existe en '{dest_path}', omitiendo descarga.")
        return dest_path

    logger.info("Descargando CSV desde Google Drive...")

    url = f"https://drive.google.com/uc?id={GOOGLE_DRIVE_FILE_ID}"
    gdown.download(url, dest_path, quiet=False)

    if not path.exists():
        raise RuntimeError("La descarga del CSV falló: el archivo no se generó.")

    size_mb = path.stat().st_size / (1024 * 1024)
    logger.info(f"Descarga completa: '{dest_path}' ({size_mb:.1f} MB)")

    return dest_path