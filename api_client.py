"""Cliente HTTP que imita la API pública de `database.py`.

Todas las operaciones van al servidor central definido en `config.json`.
Si la red cae, las llamadas lanzan `ConnectionError` con un mensaje claro.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from config import get_server_url

HORAS_SEMANA_ESTANDAR = 40

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class RemoteError(RuntimeError):
    """Error reportado por el servidor (validación, etc.)."""


def _base_url() -> str:
    url = get_server_url()
    if not url:
        raise RuntimeError(
            "Modo remoto activo pero no hay server_url en config.json."
        )
    return url


def _client() -> httpx.Client:
    return httpx.Client(base_url=_base_url(), timeout=_TIMEOUT)


def _raise_for_connection(exc: Exception) -> None:
    raise ConnectionError(
        "No se puede conectar al servidor de TimeTracker.\n"
        "Comprueba que el PC del admin está encendido, que el servidor "
        "está en marcha y que estás en la misma WiFi.\n\n"
        f"Detalle: {exc}"
    ) from exc


def _request(method: str, path: str, **kwargs) -> Any:
    try:
        with _client() as client:
            response = client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        _raise_for_connection(exc)

    if response.status_code == 204:
        return None

    if response.status_code >= 400:
        detail = None
        try:
            payload = response.json()
            detail = payload.get("detail", payload)
        except Exception:
            detail = response.text
        if isinstance(detail, list):
            detail = "; ".join(
                str(item.get("msg", item)) if isinstance(item, dict) else str(item)
                for item in detail
            )
        raise RemoteError(str(detail) or f"Error HTTP {response.status_code}")

    if not response.content:
        return None

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    return response.content


def _as_tuple(value: Any) -> Optional[tuple]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value


def _as_tuple_list(value: Any) -> list:
    if not value:
        return []
    return [tuple(row) if isinstance(row, list) else row for row in value]


# ---------------------------------------------------------------------------
# Ciclo de vida / salud
# ---------------------------------------------------------------------------

def init_db() -> None:
    """En modo remoto solo comprueba que el servidor responde."""
    try:
        with _client() as client:
            response = client.get("/health")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _raise_for_connection(exc)


# ---------------------------------------------------------------------------
# Empleados / auth
# ---------------------------------------------------------------------------

def hay_algun_admin_activo() -> bool:
    return bool(_request("GET", "/auth/has-admin"))


def autenticar(username, password):
    try:
        return _request(
            "POST",
            "/auth/login",
            json={"username": username, "password": password},
        )
    except RemoteError:
        return None


def crear_empleado(username, nombre, password, is_admin=False,
                   activo=True, password_change_required=False):
    try:
        return _request(
            "POST",
            "/empleados",
            json={
                "username": username,
                "nombre": nombre,
                "password": password,
                "is_admin": is_admin,
                "activo": activo,
                "password_change_required": password_change_required,
            },
        )
    except RemoteError as exc:
        raise ValueError(str(exc)) from exc


def cambiar_password(username, new_password, force_change_next_login=False):
    return _request(
        "POST",
        f"/empleados/{username}/password",
        json={
            "new_password": new_password,
            "force_change_next_login": force_change_next_login,
        },
    )


def listar_empleados(incluir_inactivos=True):
    return _request(
        "GET",
        "/empleados",
        params={"incluir_inactivos": str(incluir_inactivos).lower()},
    )


def obtener_empleado(username):
    try:
        return _request("GET", f"/empleados/{username}")
    except RemoteError:
        return None


def actualizar_empleado(username, nombre=None, activo=None, is_admin=None):
    body = {}
    if nombre is not None:
        body["nombre"] = nombre
    if activo is not None:
        body["activo"] = activo
    if is_admin is not None:
        body["is_admin"] = is_admin
    try:
        return _request("PATCH", f"/empleados/{username}", json=body)
    except RemoteError as exc:
        raise ValueError(str(exc)) from exc


def es_admin(usuario) -> bool:
    emp = obtener_empleado(usuario)
    return bool(emp and emp.get("is_admin"))


# ---------------------------------------------------------------------------
# Jornadas / pausas
# ---------------------------------------------------------------------------

def get_today_jornada(usuario):
    return _as_tuple(_request("GET", f"/jornadas/hoy/{usuario}"))


def create_jornada(usuario):
    return _request("POST", f"/jornadas/{usuario}")


def iniciar_pausa(jornada_id):
    return _request("POST", "/pausas/iniciar", json={"jornada_id": jornada_id})


def obtener_pausa_activa(jornada_id):
    return _as_tuple(_request("GET", f"/pausas/activa/{jornada_id}"))


def finalizar_pausa(pausa_id):
    return _request("POST", f"/pausas/{pausa_id}/finalizar")


def finalizar_jornada(jornada_id):
    return _request("POST", f"/jornadas/{jornada_id}/finalizar")


def reanudar_jornada(jornada_id):
    return _request("POST", f"/jornadas/{jornada_id}/reanudar")


def jornada_abierta(jornada_id) -> bool:
    return bool(_request("GET", f"/jornadas/{jornada_id}/abierta"))


def cerrar_jornadas_huerfanas(usuario) -> int:
    return int(_request("POST", f"/jornadas/cerrar-huerfanas/{usuario}"))


def calcular_segundos_trabajados(jornada_id) -> float:
    return float(_request("GET", f"/jornadas/{jornada_id}/segundos-trabajados"))


def calcular_segundos_pausas(jornada_id) -> float:
    return float(_request("GET", f"/jornadas/{jornada_id}/segundos-pausas"))


def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def obtener_jornadas_semana(usuario):
    return _as_tuple_list(_request("GET", f"/jornadas/semana/{usuario}"))


def obtener_jornadas_mes(usuario):
    return _as_tuple_list(_request("GET", f"/jornadas/mes/{usuario}"))


def desglose_horas_semana(jornadas):
    ids = [j[0] for j in (jornadas or [])]
    return _request("POST", "/stats/desglose-semana", json={"jornada_ids": ids})


def desglose_mes(usuario):
    return _request("GET", f"/stats/mes/{usuario}")


def desglose_por_semanas_mes(usuario):
    return _request("GET", f"/stats/semanas-mes/{usuario}")


def exportar_todos_empleados_mes_excel(filename=None):
    content = _request("GET", "/export/mes-todos")
    if filename is None:
        from datetime import datetime
        filename = f"reporte_mes_{datetime.now().strftime('%Y-%m')}_TODOS.xlsx"
    path = os.path.abspath(filename)
    with open(path, "wb") as f:
        f.write(content)
    return path
