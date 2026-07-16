"""
Hace que la app (y opcionalmente el servidor) arranquen al iniciar sesión.

Uso:
    python autostart.py enable           # app cliente en bandeja
    python autostart.py disable
    python autostart.py status

    python autostart.py enable-server    # servidor central (PC admin)
    python autostart.py disable-server
    python autostart.py status-server

Soportado:
    - macOS  (~/Library/LaunchAgents/<label>.plist)
    - Windows (%APPDATA%\\...\\Startup\\<name>.bat)
"""

import os
import sys
import platform
from pathlib import Path


APP_LABEL = "com.bruno.timetracker"
APP_NAME = "TimeTracker"
SERVER_LABEL = "com.bruno.timetracker.server"
SERVER_NAME = "TimeTrackerServer"


def project_root() -> Path:
    return Path(__file__).resolve().parent


def main_script() -> Path:
    return project_root() / "main.py"


def server_script() -> Path:
    return project_root() / "server.py"


# -------------------------------------------------------------------------
# macOS: LaunchAgent
# -------------------------------------------------------------------------

def _mac_plist_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _mac_plist_contents(label: str, script: Path, extra_args=None,
                        keep_alive: bool = False) -> str:
    python_bin = sys.executable
    workdir = str(project_root())
    log = str(project_root() / f"{label}.log")
    err = str(project_root() / f"{label}.err")
    args = [python_bin, str(script)] + (extra_args or [])
    args_xml = "\n".join(f"        <string>{a}</string>" for a in args)
    keep = "<true/>" if keep_alive else "<false/>"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>WorkingDirectory</key>
    <string>{workdir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    {keep}
    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{err}</string>
</dict>
</plist>
"""


def _mac_enable(label: str, script: Path, extra_args=None,
                keep_alive: bool = False) -> Path:
    plist = _mac_plist_path(label)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(
        _mac_plist_contents(label, script, extra_args, keep_alive),
        encoding="utf-8",
    )
    os.system(f"launchctl unload {plist} >/dev/null 2>&1")
    os.system(f"launchctl load {plist}")
    return plist


def _mac_disable(label: str) -> bool:
    plist = _mac_plist_path(label)
    if not plist.exists():
        return False
    os.system(f"launchctl unload {plist} >/dev/null 2>&1")
    plist.unlink()
    return True


def _mac_status(label: str) -> bool:
    return _mac_plist_path(label).exists()


# -------------------------------------------------------------------------
# Windows: .bat en Startup
# -------------------------------------------------------------------------

def _win_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("No se encuentra la variable APPDATA")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _win_bat_path(name: str) -> Path:
    return _win_startup_dir() / f"{name}.bat"


def _win_app_bat_contents() -> str:
    python_bin = sys.executable
    script = main_script()
    workdir = project_root()
    pyw = python_bin.replace("python.exe", "pythonw.exe")
    return (
        "@echo off\r\n"
        f"cd /d \"{workdir}\"\r\n"
        f"start \"\" \"{pyw}\" \"{script}\" --minimized\r\n"
    )


def _win_server_bat_contents() -> str:
    # Consola visible: el admin ve que el servidor está en marcha.
    python_bin = sys.executable
    script = server_script()
    workdir = project_root()
    return (
        "@echo off\r\n"
        f"cd /d \"{workdir}\"\r\n"
        f"start \"TimeTracker Server\" \"{python_bin}\" \"{script}\"\r\n"
    )


def _win_enable(name: str, contents: str) -> Path:
    bat = _win_bat_path(name)
    bat.parent.mkdir(parents=True, exist_ok=True)
    bat.write_text(contents, encoding="utf-8")
    return bat


def _win_disable(name: str) -> bool:
    bat = _win_bat_path(name)
    if not bat.exists():
        return False
    bat.unlink()
    return True


def _win_status(name: str) -> bool:
    return _win_bat_path(name).exists()


# -------------------------------------------------------------------------
# Dispatch app cliente
# -------------------------------------------------------------------------

def enable():
    system = platform.system()
    if system == "Darwin":
        path = _mac_enable(APP_LABEL, main_script(), ["--minimized"])
        print(f"Autostart app macOS instalado en:\n  {path}")
    elif system == "Windows":
        path = _win_enable(APP_NAME, _win_app_bat_contents())
        print(f"Autostart app Windows instalado en:\n  {path}")
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)


def disable():
    system = platform.system()
    if system == "Darwin":
        ok = _mac_disable(APP_LABEL)
        path = _mac_plist_path(APP_LABEL)
    elif system == "Windows":
        ok = _win_disable(APP_NAME)
        path = _win_bat_path(APP_NAME)
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)
        return

    print("Autostart app desinstalado." if ok else f"No estaba instalado ({path}).")


def status():
    system = platform.system()
    if system == "Darwin":
        installed = _mac_status(APP_LABEL)
        path = _mac_plist_path(APP_LABEL)
    elif system == "Windows":
        installed = _win_status(APP_NAME)
        path = _win_bat_path(APP_NAME)
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)
        return

    if installed:
        print(f"Autostart app INSTALADO en:\n  {path}")
    else:
        print(f"Autostart app NO instalado (debería estar en: {path})")


# -------------------------------------------------------------------------
# Dispatch servidor
# -------------------------------------------------------------------------

def enable_server():
    system = platform.system()
    if system == "Darwin":
        path = _mac_enable(
            SERVER_LABEL, server_script(), keep_alive=True
        )
        print(f"Autostart servidor macOS instalado en:\n  {path}")
    elif system == "Windows":
        path = _win_enable(SERVER_NAME, _win_server_bat_contents())
        print(f"Autostart servidor Windows instalado en:\n  {path}")
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)


def disable_server():
    system = platform.system()
    if system == "Darwin":
        ok = _mac_disable(SERVER_LABEL)
        path = _mac_plist_path(SERVER_LABEL)
    elif system == "Windows":
        ok = _win_disable(SERVER_NAME)
        path = _win_bat_path(SERVER_NAME)
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)
        return

    print(
        "Autostart servidor desinstalado."
        if ok
        else f"No estaba instalado ({path})."
    )


def status_server():
    system = platform.system()
    if system == "Darwin":
        installed = _mac_status(SERVER_LABEL)
        path = _mac_plist_path(SERVER_LABEL)
    elif system == "Windows":
        installed = _win_status(SERVER_NAME)
        path = _win_bat_path(SERVER_NAME)
    else:
        print(f"Sistema no soportado: {system}")
        sys.exit(1)
        return

    if installed:
        print(f"Autostart servidor INSTALADO en:\n  {path}")
    else:
        print(f"Autostart servidor NO instalado (debería estar en: {path})")


if __name__ == "__main__":
    commands = {
        "enable": enable,
        "disable": disable,
        "status": status,
        "enable-server": enable_server,
        "disable-server": disable_server,
        "status-server": status_server,
    }
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__)
        sys.exit(1)

    commands[sys.argv[1]]()
