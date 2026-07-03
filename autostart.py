"""
Hace que la app arranque automáticamente al iniciar sesión.

Uso:
    python autostart.py enable    # instalar autostart
    python autostart.py disable   # desinstalar autostart
    python autostart.py status    # ver si está instalado

Soportado:
    - macOS  (~/Library/LaunchAgents/<label>.plist)
    - Windows (%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\<name>.bat)
"""

import os
import sys
import platform
from pathlib import Path


APP_LABEL = "com.bruno.timetracker"
APP_NAME = "TimeTracker"


def project_root() -> Path:
    return Path(__file__).resolve().parent


def main_script() -> Path:
    return project_root() / "main.py"


# -------------------------------------------------------------------------
# macOS: LaunchAgent (~/Library/LaunchAgents/<label>.plist)
# -------------------------------------------------------------------------

def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_LABEL}.plist"


def _mac_plist_contents() -> str:
    python_bin = sys.executable
    script = str(main_script())
    workdir = str(project_root())
    log = str(project_root() / "autostart.log")
    err = str(project_root() / "autostart.err")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{APP_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_bin}</string>
        <string>{script}</string>
        <string>--minimized</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{workdir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{err}</string>
</dict>
</plist>
"""


def enable_mac() -> Path:
    plist = _mac_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(_mac_plist_contents(), encoding="utf-8")

    # Carga (o recarga) el agent.
    os.system(f"launchctl unload {plist} >/dev/null 2>&1")
    os.system(f"launchctl load {plist}")

    return plist


def disable_mac() -> bool:
    plist = _mac_plist_path()
    if not plist.exists():
        return False

    os.system(f"launchctl unload {plist} >/dev/null 2>&1")
    plist.unlink()
    return True


def status_mac() -> bool:
    return _mac_plist_path().exists()


# -------------------------------------------------------------------------
# Windows: .bat en la carpeta Startup
# -------------------------------------------------------------------------

def _win_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("No se encuentra la variable APPDATA")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _win_bat_path() -> Path:
    return _win_startup_dir() / f"{APP_NAME}.bat"


def _win_bat_contents() -> str:
    python_bin = sys.executable
    script = main_script()
    workdir = project_root()
    # `pythonw.exe` en vez de `python.exe` para no abrir consola.
    pyw = python_bin.replace("python.exe", "pythonw.exe")
    return (
        "@echo off\r\n"
        f"cd /d \"{workdir}\"\r\n"
        f"start \"\" \"{pyw}\" \"{script}\" --minimized\r\n"
    )


def enable_win() -> Path:
    bat = _win_bat_path()
    bat.parent.mkdir(parents=True, exist_ok=True)
    bat.write_text(_win_bat_contents(), encoding="utf-8")
    return bat


def disable_win() -> bool:
    bat = _win_bat_path()
    if not bat.exists():
        return False
    bat.unlink()
    return True


def status_win() -> bool:
    return _win_bat_path().exists()


# -------------------------------------------------------------------------
# Dispatch
# -------------------------------------------------------------------------

def enable():
    system = platform.system()
    if system == "Darwin":
        path = enable_mac()
        print(f"Autostart macOS instalado en:\n  {path}")
    elif system == "Windows":
        path = enable_win()
        print(f"Autostart Windows instalado en:\n  {path}")
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)


def disable():
    system = platform.system()
    if system == "Darwin":
        ok = disable_mac()
    elif system == "Windows":
        ok = disable_win()
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)
        return

    print("Autostart desinstalado." if ok else "No estaba instalado.")


def status():
    system = platform.system()
    if system == "Darwin":
        installed = status_mac()
        path = _mac_plist_path()
    elif system == "Windows":
        installed = status_win()
        path = _win_bat_path()
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)
        return

    if installed:
        print(f"Autostart INSTALADO en:\n  {path}")
    else:
        print(f"Autostart NO instalado (deber\u00eda estar en: {path})")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"enable", "disable", "status"}:
        print(__doc__)
        sys.exit(1)

    {"enable": enable, "disable": disable, "status": status}[sys.argv[1]]()
