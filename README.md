# Panel PAES

Aplicacion Streamlit para administrar una fuente maestra local de material comun
y sincronizar cambios hacia tableros PAES de alumnos.
## Interfaz actual

- Tablero horizontal estilo Kanban con una estetica minimalista inspirada en principios HIG: claridad, deferencia visual y controles sobrios.
- Bloques cristalinos con paleta blanca, celeste y turquesa.
- Lista `Resultados globales` con promedio, mediana y desviacion estandar agregada del ultimo ensayo.
- El panel de resultados tambien muestra minimo y maximo desde una base SQLite local protegida.
- La fuente maestra local permite crear listas y tarjetas sin depender de un
  tablero Trello intermedio.
- Se pueden editar titulos y descripciones de tarjetas.
- Se pueden adjuntar enlaces, imagenes y PDFs.
- Se pueden crear checklists con items.
- Cada tarjeta tiene una vista previa con descripcion, links, imagenes y checklists.
- El tablero conserva scroll horizontal nativo y tambien permite arrastrar el fondo/listas para desplazarse lateralmente.
- El contenido de cada lista se puede desplazar verticalmente arrastrando el area de tarjetas.
- El editor primero pide solo lista y titulo. La descripcion, links, imagenes y checklists son opcionales y se abren con botones.
- Al crear una tarjeta, la lista se elige desde un selector con las listas disponibles.
- Las checklists tienen titulo, descripcion opcional y link opcional clickeable a guias u otros recursos.

## Conexion Trello

Configura estas variables como variables de entorno o en
`.streamlit/secrets.toml`:

```toml
TRELLO_API_KEY = "tu_api_key"
TRELLO_TOKEN = "tu_token"
```

Trello se usa para:

- Leer tableros `PAES <Alumno>` y la lista privada `Ensayos` solo para importar
  resultados agregados.
- Sincronizar contenido comun desde SQLite local hacia tableros de alumnos.
- Respetar siempre la regla: `Ensayos` no se modifica, no se sincroniza como
  material comun y no se expone desde el panel administrador.

El archivo real `.streamlit/secrets.toml` esta excluido por `.gitignore` y no
debe subirse a GitHub. Usa `.streamlit/secrets.toml.example` solo como plantilla
sin credenciales reales.

## Login administrador

El panel exige login antes de cargar Trello o la base local. Deben existir al
menos dos usuarios en `.streamlit/secrets.toml`, guardados con hashes PBKDF2 y
no con contrasenas en texto plano.

Genera los hashes:

```powershell
py scripts\generate_password_hashes.py admin coordinacion
```

El script pedira las contrasenas sin mostrarlas en pantalla y entregara un
bloque TOML como este:

```toml
[auth.users.admin]
name = "admin"
password_hash = "pbkdf2_sha256$600000$..."

[auth.users.coordinacion]
name = "coordinacion"
password_hash = "pbkdf2_sha256$600000$..."
```

Copia ese bloque al final de `.streamlit/secrets.toml` y reinicia Streamlit.
El login usa:

- Hash PBKDF2-HMAC-SHA256 con sal unica por usuario.
- Comparacion de hashes en tiempo constante.
- Bloqueo temporal despues de 5 intentos fallidos en la sesion.
- Expiracion tras 45 minutos de inactividad.
- Secretos fuera de Git mediante `.streamlit/secrets.toml`.
- La API local que escribe en Trello solo arranca despues del login y exige un
  token efimero en cada peticion del componente. Ese token se regenera en cada
  render autenticado.

## Cifrado local

El panel exige una llave `DATA_ENCRYPTION_KEY` para cifrar logs y backups antes
de cargar Trello. Genera la llave:

```powershell
py -m pip install -r requirements.txt
py scripts\generate_encryption_key.py
```

Copia la linea generada en `.streamlit/secrets.toml`:

```toml
DATA_ENCRYPTION_KEY = "..."
```

Con esa llave:

- Los logs nuevos se guardan en `data/logs/activity.jsonl.enc`.
- Los backups nuevos de tablero se guardan como `.json.enc`.
- Los backups nuevos de SQLite se guardan como `.sqlite.enc`.
- La lectura del historial conserva compatibilidad con logs antiguos en texto
  plano, pero las nuevas escrituras son cifradas.

La base SQLite activa queda local e ignorada por Git; para evitar sobrecarga, se
cifran los respaldos y no cada consulta individual de SQLite.

La app descubre tableros abiertos `PAES <Alumno>` con `GET /members/me/boards`.
Los tableros de prueba definidos en el codigo se excluyen. Las escrituras reales
solo se hacen al aplicar una sincronizacion confirmada y nunca sobre `Ensayos`.

Lecturas:

- `GET /members/me/boards`
- `GET /boards/{id}`
- `GET /cards/{id}/checklists`

Escrituras habilitadas solo despues de validar que el destino es un tablero PAES
de alumno:

- `POST /lists`
- `POST /cards`
- `PUT /cards/{id}`
- `POST /cards/{id}/attachments`
- `POST /cards/{id}/checklists`
- `POST /checklists/{id}/checkItems`

## Privacidad de resultados

`Resultados globales` muestra solo estadisticas agregadas. No permite acceder a
datos individuales, no modifica informacion de alumnos y no reemplaza el proyecto
separado que trabaja con resultados privados.

La base local se crea automaticamente en:

```text
data/admin_paes.sqlite
```

Ese archivo esta excluido por `.gitignore` porque puede contener datos
personales de estudiantes, contenido maestro local y estado de sincronizacion.
Si existe una instalacion antigua con `data/paes_results.sqlite`, la app la
migra automaticamente al nuevo nombre al iniciar. La estructura SQL principal es:

- `students`: un registro por alumno, con `name` unico.
- `essay_scores`: pares `(student_id, essay_name, score)` con puntajes entre 0 y 1000.
- `master_lists` y `master_cards`: fuente local del material comun.
- `content_visibility`: reglas por alumno para ocultar o mostrar material.
- `new_content_delivery` y `content_delete_delivery`: mapeo seguro de entregas en Trello.

El objetivo posterior es leer en modo solo lectura la lista privada `Ensayos` de
cada tablero de alumno, extraer `(nombre estudiante, ensayo, puntaje)` y guardar
esos datos con consultas parametrizadas en SQLite. El panel de la izquierda solo
muestra agregados del ultimo ensayo: promedio, mediana, desviacion estandar,
minimo y maximo.

## Importar ensayos de alumnos

El script `scripts/import_essay_scores.py` lee, en modo solo lectura, todos los
tableros abiertos cuyo nombre empieza con `PAES` seguido del nombre del alumno.
El nombre se normaliza quitando puntos o puntuacion final del tablero: por
ejemplo, `PAES Fran U.` se guarda como `Fran U`.
Los tableros de prueba `PAES ALUMNO ESTRELLA`, `PAES alumno01`,
`PAES Prueba AutomatizaciÃ³n`, `PAES Prueba_Naty` y `PAES TEST` se excluyen por
completo: no se leen, no se interpretan y no se insertan en SQLite.
En cada tablero busca la lista `Ensayos`, interpreta tarjetas como:

```text
Ensayo 1: (67/75) 799/1000
Ensayo 6 (68/75) 814/1.000
Ensayo 3 puntaje 718
```

Los ensayos ausentes no se guardan como cero; simplemente no se inserta fila para
ese alumno y ese ensayo.

Primero revisa sin escribir:

```powershell
py scripts\import_essay_scores.py --dry-run
```

Luego importa a SQLite:

```powershell
py scripts\import_essay_scores.py
```

Opciones utiles:

```powershell
py scripts\import_essay_scores.py --dry-run --limit 5
py scripts\import_essay_scores.py --delay 0.5
```

## Vista previa de sincronizacion de material comun

La sincronizacion desde la fuente maestra local SQLite hacia tableros
`PAES <Alumno>` debe partir como plan de cambios, sin aplicar nada
automaticamente. La regla acordada es:

- Crear lista faltante.
- Crear tarjeta faltante.
- Actualizar descripcion distinta.
- Adjuntar enlace faltante.
- Adjuntar imagen faltante.
- Crear checklist faltante.
- No tocar `Ensayos`.
- No borrar nada sin confirmacion.

Para revisar un tablero sin escribir en Trello:

```powershell
py scripts\preview_sync_plan.py "PAES Fran U."
```

El plan tolera diferencias leves de formato en nombres de listas y tarjetas:
mayusculas, tildes, espacios extra, guiones y variaciones pequenas.

## Gestion de cohortes

La profesora gestiona altas y bajas directamente en Trello:

1. **Alumno nuevo**: la profesora crea un board abierto con formato
   `PAES <Nombre>`. Al actualizar/sincronizar, el panel lo registra como activo.
2. **Alumno egresado**: la profesora archiva manualmente su board en Trello. En
   la siguiente lectura, el panel lo marca localmente como `archived` sin borrar
   resultados ni historial.
3. **Entrega inicial**: si aparece un board nuevo o reabierto, el panel marca el
   material maestro local como pendiente para que el alumno pueda recibir las
   listas y tarjetas visibles en la siguiente sincronizacion confirmada.
4. **Historial conservado**: los puntajes, mappings y auditoria no se eliminan
   automaticamente. Nada se borra sin confirmacion explicita.
5. **Monitoreo**: la API local expone `/cohort-status` y `/refresh-cohorts` para
   revisar alumnos activos/archivados y forzar una lectura de boards abiertos.

## Backups y logs locales

El panel guarda auditoria local en:

```text
data/logs/activity.jsonl.enc
```

Los respaldos se guardan en:

```text
data/backups/
```

Antes de operaciones que escriben en Trello sobre tableros de alumnos, el panel
crea backups locales. Antes de reemplazar resultados importados desde `Ensayos`,
crea una copia cifrada de `data/admin_paes.sqlite`.
Estas carpetas estan ignoradas por Git para evitar subir datos privados.

Politica de retencion local:

- Logs: `activity.jsonl.enc` rota al superar 1 MB.
- Logs rotados: se conservan hasta 3 archivos (`activity.1.jsonl.enc` a `activity.3.jsonl.enc`).
- Backups: se eliminan archivos con mas de 3 dias.
- Backups: tambien se conserva como maximo los 12 archivos mas recientes.
- Backups periodicos: se intentan cada 30 minutos mientras la app esta activa.

## Ejecutar en Windows PowerShell

```powershell
cd C:\Users\pgall\Desktop\Trello_Naty\Panel_Admin_PAES\Panel_Admin_PAES
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Normalmente se abre en:

```text
http://localhost:8501
```

## Preparacion para GitHub y Streamlit Community Cloud

El repositorio queda preparado para subirse a GitHub con:

- `app.py` como entrypoint en la raiz.
- `requirements.txt` en la raiz.
- `.streamlit/config.toml` con tema base.
- `.streamlit/secrets.toml.example` como plantilla sin credenciales reales.
- `.gitignore` excluyendo secretos, bases SQLite, logs y backups.

No se debe subir:

- `.streamlit/secrets.toml`
- `data/admin_paes.sqlite`
- `data/logs/`
- `data/backups/`
- `.env` o variantes `.env.*`

Para Streamlit Community Cloud, copia el contenido real de
`.streamlit/secrets.toml` en **Advanced settings > Secrets** durante el
despliegue. No pegues credenciales en codigo ni en archivos versionados.

Para el primer despliegue en Cloud, agrega:

```toml
DISABLE_LOCAL_API = true
```

Esto evita que el navegador intente llamar una API local en `127.0.0.1`.

Limitacion importante antes de usarlo como panel operativo en Cloud:
actualmente las acciones del tablero usan una API local en `127.0.0.1` que el
componente HTML llama desde el navegador. Eso funciona en ejecucion local, pero
no es una arquitectura compatible con Community Cloud para acciones de
edicion/sincronizacion, porque el navegador del usuario no puede llamar al
`localhost` del servidor remoto. Para produccion en Cloud hay que reemplazar
esa API local por controles nativos de Streamlit, un componente con canal de
mensajes soportado o un backend externo autenticado.

La base SQLite local en Community Cloud debe considerarse estado temporal. Para
un panel operativo con historial duradero, usa una base externa gratuita o un
flujo de exportacion/importacion controlado.

Consulta DEPLOYMENT_STREAMLIT_CLOUD.md para el checklist completo.

Para despliegue operativo con SQLite persistente en una VM barata de Google Cloud, consulta deployment/GOOGLE_CLOUD_VM_SQLITE.md.

## Nota tecnica

El tablero principal se renderiza con `streamlit.components.v1.components.html`
porque el prompt inicial lo pide explicitamente. Las mutaciones reales de Trello
no se ejecutan en el componente HTML, sino en Python/Streamlit para mantener las
credenciales fuera del navegador.

## Estructura

- `app.py`: punto de entrada de Streamlit.
- `panel/auth.py`: login, hashes de contrasena y control de sesion.
- `panel/assets_cache.py`: cache local de imagenes y PDFs antes de subirlos a Trello.
- `panel/icons.py`: iconos SVG reutilizables.
- `panel/local_api.py`: API local autenticada para acciones del componente.
- `panel/master_import.py`: bootstrap local desde tableros PAES en modo solo lectura.
- `panel/renderer.py`: generacion del documento HTML/CSS/JS del tablero.
- `panel/results_db.py`: base SQLite local para master, alumnos, resultados,
  visibilidad y entregas.
- `panel/streamlit_shell.py`: configuracion Streamlit y montaje del componente.
- `panel/student_sync.py`: planificacion y aplicacion segura hacia tableros PAES.
- `panel/trello_client.py`: cliente Trello con protecciones para no tocar `Ensayos`.
- `scripts/import_essay_scores.py`: importador solo lectura de listas `Ensayos` en tableros `PAES <Alumno>`.
- `scripts/generate_password_hashes.py`: generador local de hashes para usuarios del login.






## Modo seguro VM

En Google Cloud VM usa `DISABLE_LOCAL_API = true` y `SERVER_ADMIN_NATIVE = true` en `.streamlit/secrets.toml`. Asi el panel administra SQLite y sincroniza Trello desde Python en el servidor, sin exponer una API de escritura publica.




### Modo server-side estricto

En VM se recomienda `DISABLE_LOCAL_API = true` y `SERVER_ADMIN_NATIVE = true`. En este modo, toda accion persistente ocurre desde `Panel servidor seguro`; el tablero visual inferior queda como lectura para evitar inconsistencias entre navegador, SQLite y Trello.

