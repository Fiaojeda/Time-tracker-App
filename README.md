# Time-tracker-App

Aplicación de escritorio para llevar el control de las horas trabajadas por los empleados: fichajes de entrada/salida, pausas y exportación de informes mensuales en Excel.

Puede usarse en un solo PC (SQLite local) o con **base compartida** en la oficina: un servidor en el PC del admin y el resto de PCs como clientes.

## Estructura del proyecto

- `main.py` — punto de entrada de la aplicación (login + arranque).
- `ui.py` — interfaz principal (PySide6).
- `auth_ui.py` — diálogos de login, bootstrap del primer admin, cambio de contraseña y panel de gestión de empleados.
- `database.py` — capa SQLite (usada por el servidor o en modo local).
- `data.py` — elige entre SQLite local o cliente HTTP según `config.json`.
- `api_client.py` — cliente HTTP hacia el servidor central.
- `server.py` — servidor FastAPI (PC del administrador).
- `config.py` / `config.example.json` — configuración de `server_url`.
- `autostart.py` — arranque automático de la app y del servidor.
- `assets/` — recursos (iconos, imágenes).

## Requisitos

- Python 3.10+
- Dependencias en `requirements.txt` (PySide6, pandas, openpyxl, FastAPI, etc.)

```bash
pip install -r requirements.txt
```

## Modo local (un solo PC)

Sin `config.json` (o sin `server_url`):

```bash
python main.py
```

Se crea `tracker.db` en esa máquina.

## Modo oficina (base compartida)

Todos los PCs usan la **misma** base de datos en el PC del admin. Si cae la WiFi, no se puede fichar hasta que vuelva.

### 1) PC del administrador

1. Instala dependencias (`pip install -r requirements.txt`).
2. Arranca el servidor y **deja la ventana abierta** en horario laboral:

```bash
python server.py
```

La consola muestra la URL de oficina, por ejemplo:

```text
Oficina: http://192.168.1.42:8000
```

3. Crea `config.json` en la carpeta del proyecto (copia de `config.example.json`) apuntando a localhost:

```json
{
  "server_url": "http://127.0.0.1:8000"
}
```

4. Arranca la app: `python main.py`.
5. Crea el primer admin y da de alta a los empleados.
6. (Recomendado) Arranque automático:

```bash
python autostart.py enable-server
python autostart.py enable
```

7. En Windows, permite el puerto **8000** en el Firewall la primera vez que Windows lo pida (redes privadas).

### 2) PCs de empleados

1. Misma instalación del repo + `pip install -r requirements.txt`.
2. Crea `config.json` con la URL de oficina del admin (la que salió en `server.py`):

```json
{
  "server_url": "http://192.168.1.42:8000"
}
```

3. Arranca la app: `python main.py` e inicia sesión con el usuario que el admin creó.
4. (Opcional) `python autostart.py enable` para abrirla al encender el PC.

No hace falta (ni debe) correr `server.py` en los PCs de empleados.

### Informes

Desde la app del admin, el botón de exportar genera el Excel **de todos** los empleados con los datos del servidor central.

### Migrar datos de un PC antiguo

Si ya había fichajes en un `tracker.db` local (p. ej. el de Salvatore), cópialo a la carpeta del proyecto **en el PC del admin** (sustituyendo el del servidor) **antes** de que otros empiecen a fichar en el servidor nuevo. Solo puede haber una base “oficial”.

## Empleados y autenticación

- **Primer arranque:** si aún no existe ningún administrador, la app pide crear el primero.
- **Alta de empleados:** botón *“Gestión de empleados…”* (solo admins).
- **Contraseñas:** PBKDF2-HMAC-SHA256 con sal por usuario.

## Base de datos

Fichero SQLite `tracker.db` (no se versiona). En modo oficina vive solo en el PC del admin.

Tablas: `jornadas`, `pausas`, `empleados`.
