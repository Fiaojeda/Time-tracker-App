# main.py

import sys

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from database import (
    init_db,
    get_today_jornada,
    create_jornada,
    cerrar_jornadas_huerfanas,
    hay_algun_admin_activo,
    obtener_empleado,
)
from auth_ui import (
    LoginDialog,
    BootstrapAdminDialog,
    ChangePasswordDialog,
)
from ui import TimeTrackerApp


def ensure_jornada(usuario):
    """Crea la jornada de hoy si aún no existe."""
    if not get_today_jornada(usuario):
        print("No existe jornada para hoy. Creando...")
        create_jornada(usuario)


def run_login_flow():
    """Ejecuta el flujo de autenticación.

    - Si no existe ningún admin activo, fuerza la creación del primero.
    - Si el empleado autenticado tiene `password_change_required`, obliga
      a cambiar la contraseña antes de continuar.

    Devuelve el dict del empleado autenticado, o None si el usuario cancela.
    """
    if not hay_algun_admin_activo():
        bootstrap = BootstrapAdminDialog()
        if bootstrap.exec() != QDialog.Accepted:
            return None

    login = LoginDialog()
    if login.exec() != QDialog.Accepted:
        return None

    empleado = login.empleado

    if empleado["password_change_required"]:
        cambio = ChangePasswordDialog(empleado["username"], forzado=True)
        if cambio.exec() != QDialog.Accepted:
            return None
        empleado = obtener_empleado(empleado["username"])

    return empleado


if __name__ == "__main__":

    init_db()

    # QApplication tiene que existir antes de mostrar cualquier QDialog.
    app = QApplication(sys.argv)

    # Que el cierre de la última ventana NO cierre la app (queremos que
    # siga viva en el tray).
    app.setQuitOnLastWindowClosed(False)

    empleado = run_login_flow()
    if empleado is None:
        sys.exit(0)

    usuario = empleado["username"]

    # Cierra jornadas de días anteriores que quedaron abiertas.
    cerrar_jornadas_huerfanas(usuario)
    ensure_jornada(usuario)

    window = TimeTrackerApp(empleado)

    # Mostramos la ventana sólo si el usuario la lanzó manualmente.
    # En arranque automático (autostart) se pasa "--minimized" para
    # dejarla oculta en la bandeja.
    if "--minimized" not in sys.argv:
        window.show()

    sys.exit(app.exec())
