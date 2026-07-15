# Cruz Morada — API de Estadísticas de Ventas

Servicio REST que procesa un archivo CSV de ventas y expone estadísticas
(suma, conteo, promedio, mínimo, máximo, mediana, desviación estándar)
mediante los métodos GET y POST, con filtros opcionales.

## Requisitos

- Python 3.12+
- pip

## Instalación

1. Crear y activar un entorno virtual:
```bash
   python -m venv venv
   # Mac/Linux
   source venv/bin/activate
```

2. Instalar dependencias:
```bash
   pip install -r requirements.txt
```

3. Colocar el archivo CSV de ventas en `data/ventas.csv`
   (descargar desde el enlace de Google Drive provisto en el enunciado).

## Ejecución

```bash
uvicorn app.main:app --reload
```

El servidor queda disponible en `http://127.0.0.1:8000`.