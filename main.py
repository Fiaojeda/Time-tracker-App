# main.py

import getpass
import sys

from PySide6.QtWidgets import QApplication

from database import (
    init_db,
    get_today_jornada,
    create_jornada,
    cerrar_jornadas_huerfanas,
)
from ui import TimeTrackerApp


def ensure_jornada(usuario):
    """Crea la jornada de hoy si aún no existe."""
    if not get_today_jornada(usuario):
        print("No existe jornada para hoy. Creando...")
        create_jornada(usuario)


if __name__ == "__main__":

    init_db()

    usuario = getpass.getuser()

    # Cierra jornadas de días anteriores que quedaron abiertas.
    cerrar_jornadas_huerfanas(usuario)
    ensure_jornada(usuario)

    app = QApplication(sys.argv)

    # Que el cierre de la última ventana NO cierre la app (queremos que
    # siga viva en el tray).
    app.setQuitOnLastWindowClosed(False)

    window = TimeTrackerApp()

    # Mostramos la ventana sólo si el usuario la lanzó manualmente.
    # En arranque automático (autostart) se pasa "--minimized" para
    # dejarla oculta en la bandeja.
    if "--minimized" not in sys.argv:
        window.show()

    sys.exit(app.exec())
