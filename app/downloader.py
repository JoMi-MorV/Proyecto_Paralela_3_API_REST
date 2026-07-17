"""
downloader.py

Descarga automáticamente el archivo de ventas desde Google Drive al iniciar,
lo descomprime si viene en formato .gz/.tar.gz/.zip y localiza ventas_completas.csv
para que el resto de la aplicación pueda cargarlo sin pasos manuales.
"""

import gzip
import logging
import shutil
import tarfile
import zipfile
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

# Extraído del enlace para compartir
# https://drive.google.com/file/d/1vJu8gKm7GNIy1ocx0k-tpjOL8DU3B4X9/view?usp=sharing
GOOGLE_DRIVE_FILE_ID = "1vJu8gKm7GNIy1ocx0k-tpjOL8DU3B4X9"

DATA_DIR = Path("data")
CSV_NAME = "ventas_completas.csv"
DEST_PATH = str(DATA_DIR / CSV_NAME)


def _locate_existing_csv(data_dir: Path) -> Path | None:
    """Busca ventas_completas.csv en data/ o en subcarpetas ya descomprimidas."""
    direct = data_dir / CSV_NAME
    if direct.is_file():
        return direct

    matches = sorted(data_dir.rglob(CSV_NAME))
    return matches[0] if matches else None


def _find_csv(data_dir: Path) -> Path:
    csv_path = _locate_existing_csv(data_dir)
    if csv_path is None:
        raise RuntimeError(
            f"No se encontró '{CSV_NAME}' tras descomprimir el archivo descargado."
        )
    return csv_path


def _extract_archive(archive_path: Path, extract_dir: Path) -> None:
    """Descomprime el archivo descargado dentro de extract_dir."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    name = archive_path.name.lower()

    if name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(extract_dir, filter="data")
        return

    if name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extract_dir)
        return

    if name.endswith(".gz"):
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(extract_dir, filter="data")
            return
        except tarfile.ReadError:
            out_path = extract_dir / archive_path.stem
            with gzip.open(archive_path, "rb") as src, open(out_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return

    raise RuntimeError(
        f"Formato de archivo no soportado: '{archive_path.name}'. "
        "Se esperaba .gz, .tar.gz, .tgz o .zip."
    )


def download_csv(dest_path: str = DEST_PATH, force: bool = False) -> str:
    """
    Descarga el archivo desde Google Drive, lo descomprime y devuelve la ruta
    de ventas_completas.csv listo para ser cargado por data_loader.py.
    """
    data_dir = Path(dest_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)

    if not force:
        existing = _locate_existing_csv(data_dir)
        if existing is not None:
            logger.info(f"CSV ya existe en '{existing}', omitiendo descarga.")
            return str(existing)

    logger.info("Descargando archivo desde Google Drive...")

    try:
        import gdown
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "No se encontró el módulo 'gdown'. Instala la dependencia antes de descargar el CSV."
        ) from exc

    url = f"https://drive.google.com/uc?id={GOOGLE_DRIVE_FILE_ID}"
    archive_path = Path(
        gdown.download(url, str(data_dir / ""), quiet=False)
    )

    if not archive_path.is_file():
        raise RuntimeError("La descarga falló: no se generó ningún archivo.")

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    logger.info(f"Descarga completa: '{archive_path}' ({size_mb:.1f} MB)")

    if archive_path.name == CSV_NAME:
        return str(archive_path)

    logger.info(f"Descomprimiendo '{archive_path.name}'...")
    _extract_archive(archive_path, data_dir)

    csv_path = _find_csv(data_dir)
    logger.info(f"CSV listo en '{csv_path}'")
    return str(csv_path)
