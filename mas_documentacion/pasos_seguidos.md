# Proceso de Desarrollo del Proyecto

Este documento describe, en orden cronológico, los pasos seguidos durante
el desarrollo de la API de estadísticas de ventas de Cruz Morada. El
objetivo es dejar constancia del proceso de trabajo, las dificultades
encontradas y cómo se resolvieron, complementando el documento
`DECISIONES_TECNICAS.md`, que explica el por qué de cada decisión de
diseño.

---

## Fase 1: Análisis del enunciado y elección de tecnología

Se comenzó por leer el enunciado del trabajo para identificar los
requisitos obligatorios:

- Un servicio REST con dos endpoints (`GET` y `POST`) sobre la misma ruta
  `/v1/estadisticas/ventas`.
- Carga de un archivo CSV de gran volumen (3M+ filas) de forma
  **desatendida** (sin pasos manuales).
- Procesamiento del archivo usando **programación paralela con hilos**.
- Siete estadísticas requeridas: suma, conteo, promedio, mínimo, máximo,
  mediana y desviación estándar.
- Filtros combinables: `GENERO`, `EDAD`, `CANAL`, `CODIGO_PRODUCTO`,
  `ID_PERSONA`, `LOCAL`, `FECHA_DESDE`, `FECHA_HASTA`.
- Un formato de error específico y consistente para respuestas `400` y
  `500`.
- Documentación técnica en formato Swagger.
- Entregables: código fuente en GitHub (con el académico como
  colaborador), `README.md`, `datos.json`, y pruebas unitarias.

Con base en estos requisitos se eligió **FastAPI** como framework (ver
`DECISIONES_TECNICAS.md`, sección 1), principalmente porque genera
documentación Swagger automáticamente y tiene validación de datos
integrada.

---

## Fase 2: Estructura inicial del proyecto

Se definió una estructura modular, separando responsabilidades en
archivos distintos dentro de `app/`:

- `main.py` — arranque de la aplicación y definición de endpoints.
- `data_loader.py` — carga del archivo CSV.
- `validator.py` — validación de columnas y tipos de datos.
- `stats.py` — filtrado y cálculo de estadísticas.
- `errors.py` — construcción del formato de error estándar.

Esta separación permitió desarrollar y probar cada responsabilidad de
forma independiente, y facilitó que las pruebas unitarias pudieran
apuntar directamente a la lógica de negocio (`stats.py`) sin depender del
servidor en ejecución.

---

## Fase 3: Primera versión de la carga de datos y estadísticas

Se implementó una primera versión de `data_loader.py` que leía un CSV de prueba en
bloques (`chunksize`) usando `pandas.read_csv()`, bajo el supuesto de que
el archivo tenía un formato estándar separado por comas.

En paralelo, se implementó `stats.py` con dos funciones principales:
- `apply_filters()`: aplica los filtros solicitados sobre el DataFrame.
- `compute_stats()`: calcula las siete estadísticas requeridas sobre el
  resultado filtrado.

Y `errors.py`, con una función `build_error()` que arma el cuerpo de
error en el formato exacto especificado en el enunciado.

---

## Fase 4: Primer error de carga — `ParserError` de pandas

Al ejecutar la aplicación por primera vez con una sección pequeña de 
archivo CSV real, la carga falló con:

```
pandas.errors.ParserError: Error tokenizing data. C error: Expected 2 fields in line 128, saw 3
```

Se investigó la causa revisando directamente el contenido de las líneas
problemáticas del archivo. Se identificaron varias causas posibles
(comas sin escapar dentro de campos de texto, delimitador incorrecto,
codificación con BOM) y se preparó un script de diagnóstico para
identificar cuál aplicaba en este caso específico.

---

## Fase 5: Segundo error — columna `FECHA` no encontrada

Tras un ajuste inicial, la carga avanzó más allá del error de parseo,
pero falló con:

```
KeyError: 'FECHA'
```

Este error confirmó que el archivo se estaba leyendo (todas las filas se
procesaban sin lanzar excepción), pero que los nombres de columna
resultantes no coincidían con los esperados. Se determinó que esto podía
deberse a un BOM al inicio del archivo, un delimitador distinto, o
espacios en los nombres de columna.

Para poder seguir desarrollando sin depender de tener el archivo real
completo disponible en todo momento, se generó un archivo CSV de prueba
pequeño (`ventas.csv`) con la estructura de columnas esperada, que
permitió validar el resto del pipeline (validación, filtros,
estadísticas) de forma aislada.

---

## Fase 6: Identificación del problema real — CSV con doble codificación

Al continuar con pruebas y modificaciónes con este archivo de prueba,
se identificó la causa raíz de ambos errores anteriores: el archivo no
estaba simplemente mal delimitado, sino que estaba **doblemente
codificado**.

El delimitador real de los datos es `;`, con cada campo envuelto en
comillas dobles (`""valor""`). Sin embargo, al menos un valor de la
columna `PRODUCTO` contiene una coma literal sin escapar correctamente
para ese formato. Al exportar/guardar el archivo como CSV separado por
comas, esa coma interna provocó que el escritor original dividiera cada
fila incorrectamente entre columnas, agregando además comas vacías al
final de cada línea.

Se diseñó y probó una función de reconstrucción (`_reconstruct_row`) que:
1. Lee cada línea con el módulo `csv` de Python (delimitador `,`), lo que
   revierte correctamente el escape de comillas dobles.
2. Descarta los campos vacíos sobrantes al final de la fila.
3. Vuelve a unir los fragmentos resultantes con `,` (restaurando la coma
   que pertenecía al dato original).
4. Divide ese texto reconstruido usando el delimitador real `;`.
5. Elimina las comillas sobrantes de cada campo.

Esta lógica se probó exhaustivamente contra la muestra real, incluyendo
casos con múltiples comas internas en un mismo campo, antes de
integrarla al proyecto.

---

## Fase 7: Paralelización de la reconstrucción del CSV

Dado que el archivo completo tiene más de 3 millones de filas y el
enunciado exige el uso de hilos, la función de reconstrucción se integró
usando `ThreadPoolExecutor`: el archivo se lee una vez de forma
secuencial (operación de E/S), y las filas resultantes se dividen en
lotes que se procesan en paralelo entre hasta 32 hilos.

Se documentó explícitamente la limitación conocida de este enfoque (el
GIL de Python limita el paralelismo real de CPU entre hilos), y por qué
se usó `threading` en lugar de `multiprocessing` de todas formas (ver
`DECISIONES_TECNICAS.md`, sección 3).

---

## Fase 8: Validación de datos

Se agregó `validator.py`, que se ejecuta una sola vez al iniciar la
aplicación, después de cargar los datos. Verifica:
- Que existan todas las columnas requeridas (si falta alguna, la
  aplicación no arranca).
- Que los tipos de datos sean coherentes (fechas válidas, valores
  numéricos donde corresponde).
- Reglas de sanidad a nivel de fila (por ejemplo, `UNIDADES` o
  `MONTO APLICADO` negativos, `PORCENTAJE DESCUENTO` fuera de rango
  0–1).

Las inconsistencias puntuales se registran como advertencias en los
logs, sin detener el arranque de la aplicación.

---

## Fase 9: Construcción de los endpoints GET y POST

Se completó `main.py` integrando:
- Un evento de arranque (`startup_event`) que ejecuta carga y validación
  de datos automáticamente.
- El endpoint `GET /v1/estadisticas/ventas`, que recibe los filtros como
  parámetros de consulta (query params).
- El endpoint `POST /v1/estadisticas/ventas`, que recibe los filtros como
  una lista de objetos `{"consulta": ..., "valor": ...}` en el cuerpo de
  la solicitud.
- Manejo de errores en ambos endpoints, devolviendo el formato de error
  estándar (`errors.py`) ante filtros inválidos (`400`) o fallos
  inesperados (`500`).

Ambos endpoints reutilizan las mismas funciones `apply_filters()` y
`compute_stats()`, evitando duplicar lógica de negocio.

---

## Fase 10: Pruebas manuales vía Swagger

Antes de escribir pruebas automatizadas, se verificó el comportamiento
de la API manualmente a través de la documentación interactiva
(`/docs`), confirmando:
- Que una solicitud `GET` sin filtros devuelve estadísticas sobre la
  totalidad de los datos.
- Que los filtros (individuales y combinados) devuelven resultados
  correctos y consistentes entre `GET` y `POST`.
- Que los casos de error (por ejemplo, `consultas` vacío en `POST`)
  devuelven el formato de error esperado con código `400`.

---

## Fase 11: Automatización de la descarga del archivo

A esta altura del desarrollo, surgió una duda sobre como debía funcionar
el programa, ¿Debe el archivo de entrada descargarse automáticamente? La
respuesta que se decidió seguir es que una copia del archivo se descargue
automáticamente al iniciar el programa desde una carpeta de Google Drive propia
de acceso público. En caso de no tener una forma de dejar la carpeta con acceso
público, de dejó disponible la posibilidad de colocar el archivo en la carpeta
`data/`.

Se desarrolló `downloader.py` en dos iteraciones:

1. **Primera versión**: resolución del enlace de Google Drive (incluyendo
   el token de confirmación que Drive exige para archivos grandes) y
   descarga mediante un único flujo de datos.

2. **Segunda versión**: se incorporó paralelismo real a la descarga,
   dividiendo el archivo en rangos de bytes (`Range` HTTP) descargados
   simultáneamente por hasta 32 hilos, con reintentos y espera
   exponencial ante fallos por parte, y una alternativa de respaldo
   (descarga en un solo flujo) si el servidor no soporta solicitudes por
   rangos.

---

## Fase 12: Pruebas unitarias con pytest

Se agregaron pruebas unitarias (`tests/test_stats.py`) cubriendo:
- Cálculo correcto de cada estadística individual.
- Comportamiento ante un DataFrame vacío (debe devolver ceros, no
  lanzar una excepción).
- Filtrado correcto por cada campo soportado, incluyendo filtros
  combinados.
- Que los filtros con valores inválidos lancen `ValueError`, que es lo
  que finalmente se traduce en una respuesta `400` en la API.

Durante la primera ejecución de `pytest` se presentó un error de
importación (`ModuleNotFoundError: No module named 'app'`), resuelto
agregando archivos `__init__.py` a `app/` y `tests/`, y un archivo
`pytest.ini` que define la raíz del proyecto como base para las
importaciones.

---

## Fase 13: Documentación final

Se completaron los archivos de documentación requeridos:
- `README.md`: instrucciones de instalación, ejecución, descripción de
  endpoints, filtros soportados, formato de errores y estructura del
  proyecto.
- `datos.json`: datos de ejemplo y solicitudes de prueba para `GET` y
  `POST`.
- `DECISIONES_TECNICAS.md`: justificación de las decisiones de diseño y
  alternativas consideradas.
- `PROCESO_DE_DESARROLLO.md`: registro cronológico del
  proceso de trabajo.

---