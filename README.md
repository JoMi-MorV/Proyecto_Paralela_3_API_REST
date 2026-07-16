# Cruz Morada — API de Estadísticas de Ventas

Servicio REST que descarga y procesa automáticamente un archivo CSV de
ventas y expone estadísticas (suma, conteo, promedio, mínimo, máximo,
mediana, desviación estándar) mediante los métodos GET y POST, con
filtros opcionales.

## Requisitos

- Python 3.12+
- pip

## Instalación

1. Clonar el repositorio:
```bash
   git clone https://github.com/JoMi-MorV/Proyecto_Paralela_3_API_REST
   cd Proyecto_Paralela_3_API_REST
```

2. Crear y activar un entorno virtual:
```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # Mac/Linux
   source venv/bin/activate
```

3. Instalar dependencias:
```bash
   pip install -r requirements.txt
```

No se requiere ningún paso manual adicional: el archivo de ventas se
descarga automáticamente la primera vez que se inicia el servidor
(ver sección "Carga de datos" abajo).

## Descarga del archivo

Si el archivo de base de datos se encuentra en Google Drive, debe
asegurarse de que la carpeta se encuentre disponible para descargar
de forma pública, de otra manera, se debe colocar el archivo (ya sea
.csv o .gc/.zip, etc.) en la carpeta:

Proyecto_Paralela_3_API_REST/
└─── data/ 
    └── Cargar a esta carpeta el archivo ventas_completas.csv    

## Ejecución

```bash
uvicorn app.main:app --reload
```

El servidor queda disponible en `http://127.0.0.1:8000`.

## Carga de datos (automática y desatendida)

Al iniciar, la aplicación ejecuta automáticamente, sin intervención manual:

1. **Descarga** el archivo desde Google Drive (`app/downloader.py`).
   - Se descarga en paralelo usando hasta 32 hilos mediante solicitudes
     HTTP por rangos de bytes (`Range`), dividiendo el archivo en partes
     descargadas simultáneamente.
   - Si el servidor resuelto no admite solicitudes por rangos, se recurre
     automáticamente a una descarga en un solo flujo (sin paralelismo),
     registrando esta situación en los logs.
   - Si el archivo descargado es un `.zip`, `.gz` o `.tar.gz`, se
     descomprime automáticamente y se localiza `ventas_completas.csv`
     dentro del contenido extraído.
   - Si el archivo ya existe localmente en `data/`, la descarga se omite
     en ejecuciones posteriores.
   - Si el archivo no se encuentra localmente en `data/`, y el Google Drive
     donde se encuentra el archivo no se puede acceder de forma pública, la
     aplicación se cerrará automaticamente, ya que no tiene archivos para 
	 leer.

2. **Reconstruye y carga** el CSV en memoria (`app/data_loader.py`).
   - El archivo fuente usa un formato de doble codificación no estándar
     (delimitador real `;`, con comillas dobles y comas mal escapadas
     heredadas de una exportación previa). Esto se corrige fila por fila.
   - Este trabajo se distribuye en paralelo entre hasta 32 hilos
     (`ThreadPoolExecutor`), dado el volumen del archivo (3M+ filas).

3. **Valida** la estructura y tipos de datos (`app/validator.py`).
   - Si falta una columna obligatoria, la aplicación no inicia (falla
     rápido). Valores individuales inválidos generan advertencias en los
     logs, sin detener el arranque.

Revisa la consola al iniciar el servidor para confirmar la cantidad de
filas descargadas, reconstruidas y cargadas, junto con cualquier
advertencia de validación.

## Documentación interactiva (Swagger)

Una vez el servidor está corriendo, la documentación completa de los
endpoints está disponible en:
http://127.0.0.1:8000/docs

## Endpoints

### Base
/v1/estadisticas/ventas

### GET — estadísticas con filtros por query params (opcionales)
GET /v1/estadisticas/ventas
GET /v1/estadisticas/ventas?CANAL=POS
GET /v1/estadisticas/ventas?GENERO=Femenino&LOCAL=1999

**Ejemplo con curl:**
```bash
curl "http://127.0.0.1:8000/v1/estadisticas/ventas?CANAL=POS"
```

**Respuesta exitosa (200):**
```json
{
  "suma": 1500.5,
  "conteo": 42,
  "promedio": 35.73,
  "minimo": 10.0,
  "maximo": 100.0,
  "mediana": 30.0,
  "desviacion_estandar": 25.4
}
```

### POST — estadísticas con filtros dinámicos en el body
POST /v1/estadisticas/ventas
Content-Type: application/json

**Ejemplo con curl:**
```bash
curl -X POST "http://127.0.0.1:8000/v1/estadisticas/ventas" \
  -H "Content-Type: application/json" \
  -d '{
    "consultas": [
      {"consulta": "GENERO", "valor": "Femenino"},
      {"consulta": "CANAL", "valor": "POS"}
    ]
  }'
```

**Respuesta exitosa (200):** mismo formato que GET.

## Filtros soportados

| Filtro | Tipo | Valores / formato |
|---|---|---|
| `GENERO` | string | `No especificado`, `Masculino`, `Femenino`, `Otro` |
| `EDAD` | integer | Edad en años |
| `CANAL` | string | `POS`, `WEB`, `APP`, `CCT`, `APR`, `WPR` |
| `CODIGO_PRODUCTO` | integer | SKU del producto |
| `ID_PERSONA` | string (UUID) | Código único de cliente |
| `LOCAL` | integer | Número de local |
| `FECHA_DESDE` | string (ISO-8601) | Fecha mínima de la búsqueda |
| `FECHA_HASTA` | string (ISO-8601) | Fecha máxima de la búsqueda |

Los filtros son opcionales y pueden combinarse en cualquier cantidad.

## Formato de errores

Todas las respuestas de error siguen este formato:

```json
{
  "detail": "Descripción del error",
  "instance": "/v1/estadisticas/ventas",
  "status": 400,
  "title": "Bad Request",
  "type": "https://developer.mozilla.org/es/docs/Web/HTTP/Reference/Status/400",
  "timestamp": "2026-07-16T20:44:49.201437123Z",
  "errorCode": "VF",
  "errorLabel": "Validación Fallida",
  "method": "POST"
}
```

- **400 Bad Request** (`errorCode: VF`) — filtro inválido, valor no
  convertible, o `consultas` vacío/nulo en POST.
- **500 Internal Server Error** (`errorCode: IE`) — error inesperado
  al calcular estadísticas.

## Pruebas unitarias

```bash
pytest tests/ -v
```

Las pruebas cubren `apply_filters()` y `compute_stats()` de forma
aislada, usando DataFrames de prueba pequeños en vez del CSV real, por
lo que se ejecutan instantáneamente y no dependen de que el archivo de
datos esté presente.

## Decisiones técnicas

- **Descarga paralela por rangos de bytes**: el archivo se descarga
  dividido en partes simultáneas usando hasta 32 hilos, con reintentos
  y espera exponencial por parte fallida. Si el servidor no admite esto,
  se usa una descarga en un solo flujo como respaldo.
- **Reconstrucción del CSV en paralelo**: dado el formato no estándar
  del archivo fuente (ver `data_loader.py`), cada fila debe corregirse
  antes de ser cargada. Este trabajo se distribuye entre hasta 32 hilos.
- **Sin archivos intermedios en disco**: tanto la reconstrucción del CSV
  como los cálculos estadísticos ocurren en memoria; no se genera una
  copia modificada del archivo de 3M+ filas.
- **Validación de datos**: al iniciar, se valida que existan todas las
  columnas esperadas y que los tipos de datos sean coherentes. Si falta
  una columna requerida, la aplicación no inicia (falla rápido).

## Estructura del proyecto
Proyecto_Paralela_3_API_REST/
├── app/
│   ├── main.py         # Endpoints GET/POST y arranque de la app
│   ├── downloader.py   # Descarga paralela + extracción del archivo
│   ├── data_loader.py  # Reconstrucción y carga del CSV en paralelo
│   ├── validator.py    # Validación de columnas/tipos
│   ├── stats.py        # Filtros y cálculo de estadísticas
│   └── errors.py       # Formato estándar de errores
├── data/                # El CSV se descarga aquí automáticamente
├── tests/
│   └── test_stats.py
├── datos.json            # Datos de prueba y ejemplos de solicitudes
├── pytest.ini
├── requirements.txt
└── README.md

## Autor

[Nombres de los integrantes del grupo]