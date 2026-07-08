# Time-tracker-App

Aplicación de escritorio para llevar el control de las horas trabajadas por los empleados: fichajes de entrada/salida, pausas y exportación de informes mensuales en Excel.

## Estructura del proyecto

- `main.py` — punto de entrada de la aplicación (login + arranque).
- `ui.py` — interfaz principal (PySide6).
- `auth_ui.py` — diálogos de login, bootstrap del primer admin, cambio de contraseña y panel de gestión de empleados.
- `database.py` — capa de acceso a datos (SQLite): jornadas, pausas y empleados.
- `autostart.py` — utilidades para arranque automático al iniciar sesión.
- `admins.txt` *(opcional/legado)* — lista de usuarios que serán marcados como admin al migrar por primera vez a la nueva tabla `empleados`. Después de esa migración deja de usarse.
- `Tabla jornadas.sql`, `Tabla pausas.sql` — esquemas SQL de referencia.
- `assets/` — recursos (iconos, imágenes).

## Requisitos

- Python 3.10+
- Dependencias: `PyQt5` (o `PySide6`, según se use en `ui.py`) y `openpyxl` para exportar Excel.

Instala las dependencias con:

```bash
pip install PyQt5 openpyxl
```

## Ejecución

```bash
python main.py
```

## Empleados y autenticación

La aplicación tiene un sistema de credenciales propio: cada empleado inicia sesión con su usuario y contraseña, en vez de identificarse por el usuario del sistema operativo.

- **Primer arranque:** si aún no existe ningún administrador en la base de datos, la app muestra un diálogo para crear el primer admin. A partir de ese momento el login es obligatorio.
- **Alta de empleados:** desde el botón *“Gestión de empleados…”* (visible solo para admins) se pueden crear, editar, activar/desactivar y restablecer contraseñas de empleados.
- **Contraseñas:** se guardan con PBKDF2-HMAC-SHA256 y sal por usuario. Cuando un admin resetea una contraseña, el empleado deberá cambiarla en su siguiente login.
- **Migración desde versión anterior:** al actualizar, la app crea automáticamente un empleado por cada usuario que ya tenía jornadas registradas, con contraseña temporal `cambiar` (se le forzará a cambiarla al iniciar sesión). Los usuarios listados en `admins.txt` son marcados como admin durante esta migración.

## Base de datos

La aplicación usa un fichero SQLite local llamado `tracker.db`. Este fichero **no** se versiona en el repositorio (ver `.gitignore`): se crea automáticamente en cada máquina al ejecutar la app por primera vez.

Tablas:

- `jornadas` — fichajes de entrada/salida por día y usuario.
- `pausas` — pausas asociadas a una jornada.
- `empleados` — credenciales y datos básicos de cada empleado (usuario, nombre, hash de contraseña, admin, activo, fecha de alta).
