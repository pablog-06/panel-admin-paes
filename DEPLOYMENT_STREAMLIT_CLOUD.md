# Despliegue en GitHub + Streamlit Community Cloud

Checklist para publicar el proyecto sin filtrar credenciales ni datos privados.

## 1. Preparar el repositorio

- Mantener `app.py` en la raiz del repo.
- Mantener `requirements.txt` en la raiz.
- Mantener `.streamlit/config.toml` versionado.
- Mantener `.streamlit/secrets.toml.example` versionado.
- No subir `.streamlit/secrets.toml`.
- No subir `data/`, bases SQLite, logs, backups ni `.env`.

Archivos relevantes:

```text
app.py
requirements.txt
.streamlit/config.toml
.streamlit/secrets.toml.example
panel/
scripts/
assets/
```

## 2. Crear secretos para Cloud

En local, genera:

```powershell
py scripts\generate_encryption_key.py
py scripts\generate_password_hashes.py admin coordinacion
```

Luego prepara un bloque TOML con:

```toml
TRELLO_API_KEY = "..."
TRELLO_TOKEN = "..."
DATA_ENCRYPTION_KEY = "..."
DISABLE_LOCAL_API = true

[auth.users.admin]
name = "admin"
password_hash = "pbkdf2_sha256$600000$..."

[auth.users.coordinacion]
name = "coordinacion"
password_hash = "pbkdf2_sha256$600000$..."
```

Ese bloque se pega en Streamlit Community Cloud:

```text
Create app -> Advanced settings -> Secrets
```

## 3. Subir a GitHub

Desde esta carpeta:

```powershell
git init
git add app.py panel scripts assets requirements.txt README.md DEPLOYMENT_STREAMLIT_CLOUD.md .gitignore .streamlit/config.toml .streamlit/secrets.toml.example
git commit -m "Prepare Panel PAES for Streamlit Cloud"
git branch -M main
git remote add origin https://github.com/<usuario>/<repo>.git
git push -u origin main
```

Antes de hacer `git push`, verifica:

```powershell
git status --short
git diff --cached --name-only
```

No debe aparecer `.streamlit/secrets.toml` ni `data/`.

## 4. Crear app en Streamlit Community Cloud

En Streamlit Community Cloud:

1. Conecta GitHub.
2. Crea una app nueva.
3. Selecciona el repositorio.
4. Branch: `main`.
5. Main file path: `app.py`.
6. Python version: usa la misma version que en desarrollo si esta disponible.
7. Advanced settings: pega los secretos.
8. Deploy.

## 5. Estado actual de compatibilidad

El despliegue visual/login puede prepararse con esta estructura, pero el panel
operativo completo aun tiene una limitacion importante:

- En local, el HTML llama una API Python en `http://127.0.0.1:8771`.
- En Community Cloud, ese `localhost` seria el computador del usuario, no el
  servidor remoto de Streamlit.
- Por eso las acciones de edicion/sincronizacion que dependen de `fetch()` hacia
  la API local deben refactorizarse antes de operar en Cloud.
- Mientras tanto, configura `DISABLE_LOCAL_API = true` en los secretos de Cloud
  para evitar llamadas imposibles desde el navegador.

Opciones de refactor:

- Convertir acciones criticas a widgets nativos de Streamlit.
- Crear un componente Streamlit formal con canal de mensajes soportado.
- Usar un backend externo autenticado para las mutaciones Trello.

## 6. Persistencia

`data/admin_paes.sqlite` funciona bien en local, pero no debe tratarse como
almacenamiento duradero en Community Cloud. Para un uso operativo:

- Mantener SQLite solo como cache temporal, o
- Migrar estado duradero a una base externa, o
- Implementar exportacion/importacion cifrada manual.

## 7. Validacion minima despues del deploy

- La pantalla de login aparece.
- El texto inferior de creditos aparece.
- La sesion expira a los 45 minutos.
- El panel carga sin exponer secretos.
- Los datos privados no aparecen en el repositorio.
- Las acciones de sincronizacion quedan deshabilitadas o no se usan hasta
  resolver la API local.
