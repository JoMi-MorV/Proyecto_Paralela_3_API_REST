# Decisiones Técnicas y Alternativas Consideradas

Este documento explica las decisiones de diseño más importantes tomadas
durante el desarrollo de la API, junto con las alternativas que se
consideraron y por qué se descartaron. El objetivo es dejar registro del
razonamiento detrás del código, no solo el resultado final.

---

## 1. Framework web: FastAPI vs. Flask vs. Django

**Decisión: FastAPI**

| Criterio | FastAPI | Flask | Django (DRF) |
|---|---|---|---|
| Documentación Swagger | Automática, generada desde el código | Requiere `flask-swagger` u otra librería externa | Requiere `drf-yasg` u otra librería externa |
| Validación de datos | Integrada (Pydantic) | Manual o vía `marshmallow`/`Cerberus` | Integrada (serializers), pero más verboso |
| Rendimiento (async) | Nativo (ASGI, `async def`) | Requiere extensiones para async | Soporte async parcial, más reciente |
| Curva de aprendizaje | Baja-media | Baja | Alta (mucho más que lo necesario para esta API) |
| Adecuado para una API pequeña con 1-2 endpoints | Sí | Sí | Excesivo para el alcance del proyecto |

**Por qué se descartó Flask:** Flask es más minimalista y también habría
sido una opción razonable para este proyecto. Sin embargo, uno de los
requisitos explícitos del enunciado es entregar documentación técnica en
formato Swagger. Con Flask, esto habría requerido integrar una librería
adicional (`flasgger`, `flask-swagger-ui`) y mantener manualmente la
especificación OpenAPI. FastAPI genera esta documentación automáticamente
a partir de los tipos de datos y docstrings ya presentes en el código,
sin trabajo adicional.

**Por qué se descartó Django/DRF:** Django está diseñado para aplicaciones
con múltiples modelos de datos, autenticación de usuarios, panel de
administración, y ORM completo. Este proyecto expone un único recurso de
solo lectura sobre un archivo CSV en memoria; usar Django habría
significado configurar infraestructura (ORM, migraciones, apps) que el
proyecto no necesita.

---

## 2. Procesamiento de datos: pandas vs. Dask vs. NumPy puro

**Decisión: pandas**

Inicialmente se propuso una implementación alternativa usando
**Dask** (`dask.dataframe`), que permite operaciones perezosas
(*lazy evaluation*) y paralelización automática mediante un
planificador de tareas interno.

**Ventajas de Dask que se evaluaron:**
- Paralelismo real a nivel de particiones del DataFrame, no limitado por
  el GIL de Python de la misma forma que `threading`.
- Permite combinar múltiples cálculos (`sum`, `mean`, `std`, etc.) en una
  sola llamada `dask.compute(...)`, evitando recorrer el dataset una vez
  por cada estadística.

**Por qué se optó por pandas de todas formas:**
1. **Alcance del dataset**: 3 millones de filas es un volumen que pandas
   maneja cómodamente en memoria en una máquina de desarrollo estándar;
   Dask está pensado para datasets que exceden la memoria RAM disponible
   o que se procesan distribuidos entre varias máquinas, lo cual no es
   el caso aquí.
2. **Complejidad de depuración**: la evaluación perezosa de Dask hace que
   los errores (por ejemplo, del CSV con formato no estándar que se debió
   corregir manualmente) sean más difíciles de rastrear, ya que el error
   solo aparece en el momento de `.compute()`, no en el momento en que la
   operación fue escrita.
3. **Cumplimiento explícito del requisito de "hilos"**: el enunciado pide
   específicamente el uso de programación paralela mediante hilos. La
   implementación con `ThreadPoolExecutor` deja este requisito
   explícito y visible en el código (`app/data_loader.py`), mientras que
   el paralelismo de Dask ocurre de forma interna y menos demostrable
   directamente como "uso de hilos".

**Por qué no NumPy puro:** habría requerido reimplementar manualmente el
parseo de fechas, filtrado por múltiples condiciones y las siete
estadísticas requeridas, funcionalidad que pandas ya provee de forma
optimizada (internamente basada en NumPy) y con una API mucho más legible.

---

## 3. Paralelismo: `threading` vs. `multiprocessing` vs. `asyncio`

**Decisión: `threading` (vía `ThreadPoolExecutor`)**

| Enfoque | Paralelismo real (CPU) | Adecuado para I/O (red, disco) | Complejidad |
|---|---|---|---|
| `threading` | Limitado por el GIL | Sí | Baja |
| `multiprocessing` | Sí (procesos separados) | Sí, pero con más overhead | Media-alta |
| `asyncio` | No (concurrencia, no paralelismo) | Sí, muy eficiente | Media |

**Por qué no `multiprocessing`:** ofrece paralelismo real de CPU al
evitar el GIL, ya que cada proceso tiene su propio intérprete de Python.
Sin embargo, esto tiene costos importantes: cada proceso requiere su
propia copia de memoria (mayor uso de RAM al duplicar el DataFrame en
cada proceso), y la comunicación entre procesos (paso de datos, resultados)
es más costosa que compartir memoria entre hilos. Además, el enunciado
del proyecto solicita explícitamente **hilos**, no procesos.

**Por qué no `asyncio` puro:** `asyncio` brinda concurrencia (alternar
entre tareas mientras se espera E/S), no paralelismo real.

**Dónde se usó `threading` específicamente:**
- `app/data_loader.py`: reconstrucción de las filas del CSV (formato no
  estándar) distribuida en lotes entre hasta 32 hilos.
- `app/downloader.py`: descarga del archivo dividida en rangos de bytes,
  descargados en paralelo por hasta 32 hilos, con reintentos y espera
  exponencial por parte fallida.

---

## 4. Corrección del formato del CSV: reconstrucción en memoria vs. archivo intermedio

**Decisión: reconstrucción completa en memoria, sin escribir un CSV limpio a disco**

Se consideró la alternativa de leer el CSV original, corregir su formato,
y escribir un segundo archivo `.csv` ya limpio para luego cargarlo con
`pandas.read_csv()` de forma estándar.

**Por qué se descartó:**
- Con más de 3 millones de filas, escribir un archivo intermedio duplica
  el trabajo de E/S de disco (una escritura completa adicional, más una
  lectura completa adicional del archivo ya limpio).
- No aporta ningún beneficio funcional: el objetivo final es tener un
  DataFrame en memoria, y escribir a disco solo para volver a leerlo es
  un paso innecesario dado que el archivo no se reutiliza entre
  ejecuciones de la aplicación (se descarga y procesa una vez al inicio).

**Alternativa considerada y descartada: usar `engine="python"` de pandas
con manejo de errores más permisivo.** Se evaluó inicialmente cambiar el
motor de lectura de pandas a `engine="python"` (más tolerante a
inconsistencias) en lugar de reconstruir manualmente cada fila. Se
descartó porque:
1. Es significativamente más lento que el motor por defecto (`engine="c"`),
   lo cual es contraproducente para un archivo de 3M+ filas.
2. No resuelve el problema real: el archivo no tiene un delimitador
   simplemente "difícil" de detectar, sino que está doblemente codificado
   (el delimitador real es `;`, envuelto incorrectamente como si fuera un
   CSV separado por comas). ningún motor de pandas revierte esa
   codificación automáticamente; se requiere lógica específica.

---

## 5. Descarga del archivo: descarga paralela por rangos vs. `gdown` simple

**Decisión: descarga paralela por rangos de bytes (`Range` HTTP), con
respaldo a descarga de un solo flujo**

Se implementó manualmente la resolución del enlacede Google Drive 
(extracción del token de confirmación desde las cookies o
el HTML de advertencia), seguida de una verificación de si el servidor
soporta solicitudes `Range`. Si las soporta, el archivo se descarga
dividido en partes simultáneas entre hasta 32 hilos; si no las soporta,
se recurre automáticamente a una descarga en un solo flujo, evitando que
la aplicación falle si el servidor no coopera con la descarga paralela.

**Compromiso reconocido:** no todos los servidores (incluido, en algunos
casos, Google Drive tras la resolución del token) garantizan soporte de
`Range`. Por eso el diseño incluye una alternativa segura en lugar de
asumir que el paralelismo siempre será posible.

---

## 6. Formato de columnas: renombrado post-carga vs. modificar `validator.py`/`stats.py`

**Decisión: renombrar columnas después de la reconstrucción del CSV**
(`RENAME_MAP` en `data_loader.py`), en lugar de modificar los nombres de
columna esperados en `validator.py` y `stats.py`.

**Por qué:** el archivo real usa nombres como `FECHA NACIMIENTO` (con
espacio) y `GENERO` (sin tilde), mientras que el resto del código ya
usaba `FECHA_NACIMIENTO` y `GÉNERO` como nombres canónicos internos.
Se optó por adaptar los datos de entrada a un estándar interno fijo, en
lugar de propagar los nombres "crudos" del archivo por todo el código.
Esto aísla el conocimiento sobre el formato específico del archivo fuente
en un solo lugar (`data_loader.py`), facilitando que si el archivo
cambia de formato en el futuro, solo sea necesario actualizar un mapeo.

---

## 7. Manejo de filas y valores inválidos: omitir vs. rechazar la carga completa

**Decisión: omitir filas individuales malformadas y valores fuera de
rango, registrando advertencias, en lugar de detener la aplicación**

**Alternativa descartada:** hacer que cualquier fila o valor inválido
detenga por completo la carga de datos (`raise` inmediato).

**Por qué se descartó:** en un archivo de más de 3 millones de filas
proveniente de datos reales, es esperable que existan algunas
inconsistencias puntuales (por ejemplo, una fila truncada, o un
porcentaje de descuento fuera de rango). Rechazar la carga completa por
un pequeño número de filas problemáticas haría que la aplicación fuera
extremadamente frágil ante datos reales. En cambio, se distingue entre:
- **Errores estructurales graves** (falta una columna requerida por
  completo): detienen el arranque, porque la API no puede garantizar
  resultados correctos sin esa columna.
- **Inconsistencias puntuales** (una fila no reconstruible, un valor
  fuera de rango): se registran como advertencia y se excluyen del
  cálculo, pero no detienen la aplicación.

Este criterio se documenta explícitamente en los logs de inicio y en el
README, para que sea una decisión visible y no un comportamiento oculto.

---

## 8. Formato de respuesta de error

**Decisión: estructura fija de error (`detail`, `instance`, `status`,
`title`, `type`, `timestamp`, `errorCode`, `errorLabel`, `method`),
construida manualmente en `app/errors.py`**

Se consideró usar el manejo de excepciones por defecto de FastAPI
(`HTTPException`), que genera automáticamente una respuesta con la forma
`{"detail": "..."}`.

**Por qué no se usó el formato por defecto:** el enunciado especifica un
formato de error propio y más detallado, que no coincide con el formato
por defecto de FastAPI. Se optó por construir manualmente el cuerpo del
error en cada endpoint, en lugar de intentar personalizar globalmente el
manejador de excepciones de FastAPI, para mantener el control explícito
sobre cuándo se usa el código de error `VF` (validación fallida) versus
`IE` (error interno).

---

## Resumen

En términos generales, las decisiones de este proyecto priorizaron:
1. **Cumplir explícitamente los requisitos del enunciado** (hilos, no
   procesos; documentación Swagger automática; formato de error
   específico) por sobre alternativas técnicamente más sofisticadas pero
   menos alineadas con lo solicitado.
2. **Robustez ante datos reales imperfectos**, sin ocultar los problemas
   encontrados (se registran, no se silencian).
3. **Simplicidad proporcional al tamaño del problema**: se evitaron
   herramientas diseñadas para escalas mucho mayores (Dask, Django,
   multiprocessing) cuando el volumen de datos y el alcance del proyecto
   no las justificaban.
