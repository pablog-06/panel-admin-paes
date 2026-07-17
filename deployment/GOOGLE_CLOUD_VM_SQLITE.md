# Google Cloud VM + SQLite

Decision recomendada para minimizar costo y conservar SQLite:

- Compute Engine `e2-micro`.
- Region Free Tier: `us-central1`, `us-east1` o `us-west1`.
- Disco: `pd-standard`, 10 a 30 GB maximo.
- Sistema: Ubuntu 24.04 LTS.
- Base: `data/admin_paes.sqlite` en el disco persistente de la VM.
- No usar Cloud SQL.

## Costo esperado

Componentes Free Tier si se configuran bien:

- 1 VM `e2-micro` corriendo todo el mes: USD 0.
- Hasta 30 GB-month de Persistent Disk standard: USD 0.
- 1 GB/mes de salida desde Norteamerica: USD 0.

Costo que probablemente si aparece:

- IPv4 externa en uso: aprox. USD 0.005/hora.
- 24/7 equivale a aprox. USD 3.65/mes.

Estimacion prudente:

```text
Uso bajo, con IPv4 publica: USD 3.65 a 5/mes
Uso bajo, sin errores de region/disco: no deberia superar USD 5/mes
```

Para tu tarjeta virtual con poco saldo, configura un Budget Alert de USD 5 antes
de crear recursos.

## Configuracion de VM recomendada

En Google Cloud Console:

1. Compute Engine > VM instances > Create instance.
2. Name: `panel-admin-paes`.
3. Region: `us-central1`.
4. Zone: cualquier zona de `us-central1`.
5. Machine type: `e2-micro`.
6. Boot disk: Ubuntu 24.04 LTS.
7. Disk type: `Standard persistent disk` (`pd-standard`).
8. Disk size: 10 GB o 20 GB. No uses Balanced/SSD si quieres minimizar costo.
9. Firewall: permitir HTTP/HTTPS solo si usaras proxy. Para prueba rapida puedes abrir TCP 8501, pero no es ideal a largo plazo.

## Instalacion en la VM

Conectate por SSH y ejecuta:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git unzip
sudo mkdir -p /opt/panel-admin-paes
sudo chown $USER:$USER /opt/panel-admin-paes
cd /opt/panel-admin-paes
```

Luego clona el repo:

```bash
git clone https://github.com/TU_USUARIO/TU_REPO.git .
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Secrets en la VM

Crea el archivo real de secretos:

```bash
mkdir -p .streamlit
nano .streamlit/secrets.toml
```

Contenido ejemplo:

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

Para el primer despliegue seguro en VM dejamos `DISABLE_LOCAL_API = true`. Asi conservas SQLite persistente y acceso multi-dispositivo al panel sin exponer endpoints de escritura. La edicion/sincronizacion remota completa requiere una etapa adicional: mover la API de mutaciones detras de HTTPS/proxy autenticado o reemplazarla por controles nativos de Streamlit.

## Subir SQLite desde tu PC

En Windows, desde la carpeta local del proyecto:

```powershell
pwsh scripts/export_for_vm.ps1
```

Eso crea un `.zip` en `exports/` con:

- `data/admin_paes.sqlite`
- `assets/synced_trello_images/` si existe
- `assets/synced_trello_files/` si existe

No incluye `.streamlit/secrets.toml`.

Sube el zip a la VM:

```bash
gcloud compute scp exports/panel_paes_vm_data_YYYYMMDD_HHMMSS.zip panel-admin-paes:/tmp/ --zone us-central1-a
```

En la VM:

```bash
cd /opt/panel-admin-paes
unzip -o /tmp/panel_paes_vm_data_YYYYMMDD_HHMMSS.zip -d .
```

## Probar manualmente

```bash
cd /opt/panel-admin-paes
source .venv/bin/activate
python -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
```

Abre:

```text
http://IP_PUBLICA:8501
```

## Dejar corriendo con systemd

Copia la unidad:

```bash
sudo cp deployment/panel-paes.service /etc/systemd/system/panel-paes.service
sudo systemctl daemon-reload
sudo systemctl enable panel-paes
sudo systemctl start panel-paes
sudo systemctl status panel-paes
```

Logs:

```bash
journalctl -u panel-paes -f
```

## Politica de espacio para disco de 10 GB

La app queda configurada con retencion conservadora:

- Log activo: maximo 1 MB.
- Logs rotados: maximo 3 archivos.
- Backups cifrados internos: maximo 3 dias.
- Backups cifrados internos: maximo 12 archivos.

Esto mantiene `data/logs/` alrededor de pocos MB. El espacio mas importante lo
usaran `data/admin_paes.sqlite` y assets sincronizados. Para revisar uso en la VM:

```bash
du -h --max-depth=2 /opt/panel-admin-paes/data /opt/panel-admin-paes/assets | sort -h
```
## Backups de SQLite

Minimo recomendado:

```bash
mkdir -p /opt/panel-admin-paes/vm_backups
sqlite3 /opt/panel-admin-paes/data/admin_paes.sqlite ".backup '/opt/panel-admin-paes/vm_backups/admin_paes_$(date +%Y%m%d_%H%M%S).sqlite'"
```

A futuro conviene automatizar esto con cron y descargar backups periodicamente a
tu computador.

## Riesgos a evitar

- No usar Cloud SQL si el objetivo es costo minimo.
- No usar disco Balanced o SSD para Free Tier.
- No usar region Santiago si buscas Free Tier.
- No subir `.streamlit/secrets.toml` a GitHub.
- Configurar Budget Alert de USD 5.




