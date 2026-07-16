"""Servidor central de TimeTracker (FastAPI).

Ejecutar en el PC del administrador:

    python server.py

Escucha en todas las interfaces (0.0.0.0:8000) para que el resto de PCs
de la oficina puedan conectar por WiFi. La base SQLite (`tracker.db`)
vive solo en esta máquina.
"""

from __future__ import annotations

import socket
from contextlib import asynccontextmanager
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init_db()
    yield


app = FastAPI(
    title="TimeTracker Server",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Modelos de petición
# ---------------------------------------------------------------------------

class LoginBody(BaseModel):
    username: str
    password: str


class EmpleadoCreate(BaseModel):
    username: str
    nombre: str
    password: str
    is_admin: bool = False
    activo: bool = True
    password_change_required: bool = False


class EmpleadoUpdate(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None
    is_admin: Optional[bool] = None


class PasswordBody(BaseModel):
    new_password: str
    force_change_next_login: bool = False


class PausaBody(BaseModel):
    jornada_id: int


class DesgloseSemanaBody(BaseModel):
    jornada_ids: list[int] = Field(default_factory=list)


@app.get("/health")
def health():
    return {"ok": True}

# ---------------------------------------------------------------------------
# Auth / empleados
# ---------------------------------------------------------------------------

@app.get("/auth/has-admin")
def has_admin() -> bool:
    return database.hay_algun_admin_activo()


@app.post("/auth/login")
def login(body: LoginBody):
    empleado = database.autenticar(body.username, body.password)
    if empleado is None:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    return empleado


@app.post("/empleados")
def crear_empleado(body: EmpleadoCreate):
    try:
        database.crear_empleado(
            username=body.username,
            nombre=body.nombre,
            password=body.password,
            is_admin=body.is_admin,
            activo=body.activo,
            password_change_required=body.password_change_required,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/empleados")
def listar_empleados(incluir_inactivos: bool = True):
    return database.listar_empleados(incluir_inactivos=incluir_inactivos)


@app.get("/empleados/{username}")
def obtener_empleado(username: str):
    emp = database.obtener_empleado(username)
    if emp is None:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return emp


@app.patch("/empleados/{username}")
def actualizar_empleado(username: str, body: EmpleadoUpdate):
    try:
        database.actualizar_empleado(
            username,
            nombre=body.nombre,
            activo=body.activo,
            is_admin=body.is_admin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/empleados/{username}/password")
def cambiar_password(username: str, body: PasswordBody):
    database.cambiar_password(
        username,
        body.new_password,
        force_change_next_login=body.force_change_next_login,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Jornadas / pausas
# ---------------------------------------------------------------------------

@app.get("/jornadas/hoy/{usuario}")
def jornada_hoy(usuario: str) -> Optional[list[Any]]:
    row = database.get_today_jornada(usuario)
    return list(row) if row else None


@app.post("/jornadas/{usuario}")
def crear_jornada(usuario: str):
    database.create_jornada(usuario)
    return {"ok": True}


@app.post("/jornadas/{jornada_id}/finalizar")
def finalizar_jornada(jornada_id: int):
    database.finalizar_jornada(jornada_id)
    return {"ok": True}


@app.post("/jornadas/{jornada_id}/reanudar")
def reanudar_jornada(jornada_id: int):
    database.reanudar_jornada(jornada_id)
    return {"ok": True}


@app.get("/jornadas/{jornada_id}/abierta")
def jornada_abierta(jornada_id: int) -> bool:
    return database.jornada_abierta(jornada_id)


@app.post("/jornadas/cerrar-huerfanas/{usuario}")
def cerrar_huerfanas(usuario: str) -> int:
    return database.cerrar_jornadas_huerfanas(usuario)


@app.get("/jornadas/{jornada_id}/segundos-trabajados")
def segundos_trabajados(jornada_id: int) -> float:
    return database.calcular_segundos_trabajados(jornada_id)


@app.get("/jornadas/{jornada_id}/segundos-pausas")
def segundos_pausas(jornada_id: int) -> float:
    return database.calcular_segundos_pausas(jornada_id)


@app.get("/jornadas/semana/{usuario}")
def jornadas_semana(usuario: str) -> list[list[Any]]:
    return [list(row) for row in database.obtener_jornadas_semana(usuario)]


@app.get("/jornadas/mes/{usuario}")
def jornadas_mes(usuario: str) -> list[list[Any]]:
    return [list(row) for row in database.obtener_jornadas_mes(usuario)]


@app.post("/pausas/iniciar")
def iniciar_pausa(body: PausaBody):
    database.iniciar_pausa(body.jornada_id)
    return {"ok": True}


@app.get("/pausas/activa/{jornada_id}")
def pausa_activa(jornada_id: int) -> Optional[list[Any]]:
    row = database.obtener_pausa_activa(jornada_id)
    return list(row) if row else None


@app.post("/pausas/{pausa_id}/finalizar")
def finalizar_pausa(pausa_id: int):
    database.finalizar_pausa(pausa_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Estadísticas / export
# ---------------------------------------------------------------------------

@app.post("/stats/desglose-semana")
def desglose_semana(body: DesgloseSemanaBody):
    jornadas = [(jid, None, None, None) for jid in body.jornada_ids]
    return database.desglose_horas_semana(jornadas)


@app.get("/stats/mes/{usuario}")
def stats_mes(usuario: str):
    return database.desglose_mes(usuario)


@app.get("/stats/semanas-mes/{usuario}")
def stats_semanas_mes(usuario: str):
    semanas = database.desglose_por_semanas_mes(usuario)
    # date -> str para JSON
    resultado = []
    for s in semanas:
        item = dict(s)
        if hasattr(item.get("lunes"), "isoformat"):
            item["lunes"] = item["lunes"].isoformat()
        if hasattr(item.get("domingo"), "isoformat"):
            item["domingo"] = item["domingo"].isoformat()
        resultado.append(item)
    return resultado


@app.get("/export/mes-todos")
def export_mes_todos():
    filename = database.exportar_todos_empleados_mes_excel()
    return FileResponse(
        path=filename,
        filename=filename,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )


# ---------------------------------------------------------------------------
# Utilidades de red / entrada
# ---------------------------------------------------------------------------

def _local_ips() -> list[str]:
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass

    # Fallback: conectar a un DNS público solo para descubrir la IP de salida
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and ip not in ips:
            ips.insert(0, ip)
    except OSError:
        pass

    return ips or ["127.0.0.1"]


def main():
    database.init_db()
    port = 8000
    ips = _local_ips()
    print("=" * 60)
    print("  TimeTracker Server")
    print("=" * 60)
    print(f"  Local:   http://127.0.0.1:{port}")
    for ip in ips:
        print(f"  Oficina: http://{ip}:{port}")
    print()
    print("  En los otros PCs, pon esa URL de 'Oficina' en config.json")
    print("  como server_url.")
    print("  Deja esta ventana ABIERTA mientras se use la app.")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
