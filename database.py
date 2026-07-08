# database.py

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, date


DB_NAME = "tracker.db"
ADMINS_FILE = "admins.txt"

HORAS_SEMANA_ESTANDAR = 40  # tope semanal a partir del cual se cuenta como extra

# Hashing de contraseñas: PBKDF2-HMAC-SHA256 con sal por usuario.
# Formato almacenado: "pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>"
_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERS = 200_000
_PBKDF2_SALT_BYTES = 16
_PBKDF2_HASH_BYTES = 32


def get_connection():
    return sqlite3.connect(DB_NAME)


def _admins_path():
    """Ruta absoluta al fichero admins.txt (junto a este database.py)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ADMINS_FILE)


def _leer_admins_txt():
    """Lee el conjunto de usuarios administradores desde `admins.txt`.

    Se usa solo para migrar a la base de datos la primera vez que se arranca
    la nueva versión con tabla `empleados`. En la app en marcha, los admins
    viven en la BD (columna `empleados.is_admin`).
    """
    path = _admins_path()
    if not os.path.exists(path):
        return set()

    admins = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                admins.add(linea)
    except OSError:
        return set()

    return admins


def es_admin(usuario):
    """True si `usuario` está marcado como admin en la tabla `empleados`."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_admin FROM empleados WHERE username = ?",
        (usuario,),
    )
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0])


# ---------------------------------------------------------------------------
# Hashing de contraseñas
# ---------------------------------------------------------------------------

def _hash_password(password):
    """Devuelve el hash serializado de `password` con sal aleatoria."""
    salt = secrets.token_bytes(_PBKDF2_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS, _PBKDF2_HASH_BYTES
    )
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERS}${salt.hex()}${derived.hex()}"


def _verify_password(password, stored):
    """True si `password` coincide con el hash serializado `stored`."""
    if not stored:
        return False
    try:
        algo, iters_str, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False

    if algo != _PBKDF2_ALGO:
        return False

    try:
        iters = int(iters_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False

    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iters, len(expected)
    )
    return hmac.compare_digest(derived, expected)


# ---------------------------------------------------------------------------
# Empleados (CRUD + autenticación)
# ---------------------------------------------------------------------------

def _row_to_empleado(row):
    """Convierte una fila de `empleados` en un dict."""
    if row is None:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "nombre": row[2],
        "activo": bool(row[3]),
        "is_admin": bool(row[4]),
        "fecha_alta": row[5],
        "password_change_required": bool(row[6]),
    }


_EMPLEADO_COLS = (
    "id, username, nombre, activo, is_admin, fecha_alta, password_change_required"
)


def crear_empleado(username, nombre, password, is_admin=False,
                   activo=True, password_change_required=False):
    """Crea un empleado. Lanza `ValueError` si el username ya existe."""
    username = (username or "").strip()
    nombre = (nombre or "").strip()

    if not username:
        raise ValueError("El nombre de usuario es obligatorio.")
    if not nombre:
        raise ValueError("El nombre del empleado es obligatorio.")
    if not password:
        raise ValueError("La contraseña es obligatoria.")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM empleados WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        raise ValueError(f"Ya existe un empleado con el usuario '{username}'.")

    cursor.execute(
        """
        INSERT INTO empleados (
            username, nombre, password_hash, activo, is_admin,
            fecha_alta, password_change_required
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            nombre,
            _hash_password(password),
            1 if activo else 0,
            1 if is_admin else 0,
            datetime.now().isoformat(timespec="seconds"),
            1 if password_change_required else 0,
        ),
    )

    conn.commit()
    conn.close()


def autenticar(username, password):
    """Valida credenciales.

    Devuelve el dict del empleado si son correctas y está activo.
    Devuelve `None` en cualquier otro caso (usuario inexistente,
    contraseña incorrecta o empleado dado de baja).
    """
    username = (username or "").strip()
    if not username or not password:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {_EMPLEADO_COLS}, password_hash FROM empleados WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    stored_hash = row[-1]
    if not _verify_password(password, stored_hash):
        return None

    empleado = _row_to_empleado(row[:-1])
    if not empleado["activo"]:
        return None

    return empleado


def cambiar_password(username, new_password, force_change_next_login=False):
    """Actualiza la contraseña de un empleado.

    - Si `force_change_next_login` es False (caso normal, cuando el propio
      empleado cambia su contraseña), se limpia `password_change_required`.
    - Si es True (típico de un reseteo hecho por un admin), se activa el
      flag para que el empleado deba cambiarla en su siguiente login.
    """
    if not new_password:
        raise ValueError("La contraseña no puede estar vacía.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE empleados
        SET password_hash = ?, password_change_required = ?
        WHERE username = ?
        """,
        (
            _hash_password(new_password),
            1 if force_change_next_login else 0,
            username,
        ),
    )
    conn.commit()
    filas = cursor.rowcount
    conn.close()

    if filas == 0:
        raise ValueError(f"No existe el empleado '{username}'.")


def listar_empleados(incluir_inactivos=True):
    """Devuelve la lista de empleados (dicts), ordenada por nombre."""
    conn = get_connection()
    cursor = conn.cursor()

    if incluir_inactivos:
        cursor.execute(
            f"SELECT {_EMPLEADO_COLS} FROM empleados ORDER BY nombre COLLATE NOCASE"
        )
    else:
        cursor.execute(
            f"SELECT {_EMPLEADO_COLS} FROM empleados "
            f"WHERE activo = 1 ORDER BY nombre COLLATE NOCASE"
        )

    empleados = [_row_to_empleado(r) for r in cursor.fetchall()]
    conn.close()
    return empleados


def obtener_empleado(username):
    """Devuelve el dict del empleado o None si no existe."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {_EMPLEADO_COLS} FROM empleados WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_empleado(row)


def actualizar_empleado(username, nombre=None, activo=None, is_admin=None):
    """Actualiza los campos indicados. Solo cambia los que reciben valor."""
    campos = []
    valores = []

    if nombre is not None:
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El nombre no puede estar vacío.")
        campos.append("nombre = ?")
        valores.append(nombre)

    if activo is not None:
        campos.append("activo = ?")
        valores.append(1 if activo else 0)

    if is_admin is not None:
        campos.append("is_admin = ?")
        valores.append(1 if is_admin else 0)

    if not campos:
        return

    valores.append(username)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE empleados SET {', '.join(campos)} WHERE username = ?",
        valores,
    )
    conn.commit()
    filas = cursor.rowcount
    conn.close()

    if filas == 0:
        raise ValueError(f"No existe el empleado '{username}'.")


def hay_algun_admin_activo():
    """True si existe al menos un admin activo (bootstrap inicial)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM empleados WHERE is_admin = 1 AND activo = 1 LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def _tabla_empleados_esta_vacia(cursor):
    cursor.execute("SELECT 1 FROM empleados LIMIT 1")
    return cursor.fetchone() is None


def _migrar_empleados_desde_datos_existentes(cursor):
    """Bootstrap suave la primera vez que existe la tabla `empleados`.

    - Crea un empleado por cada `usuario` distinto encontrado en `jornadas`,
      con nombre = username y contraseña temporal marcada como
      `password_change_required` para que la actualicen al primer login.
    - Marca como admin a los usuarios listados en `admins.txt`.

    La contraseña temporal es "cambiar" — el flag obliga a cambiarla.
    """
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='jornadas'"
    )
    tiene_jornadas = cursor.fetchone() is not None
    if not tiene_jornadas:
        return

    cursor.execute("SELECT DISTINCT usuario FROM jornadas WHERE usuario IS NOT NULL")
    usuarios = [row[0] for row in cursor.fetchall() if row[0]]
    if not usuarios:
        return

    admins_txt = _leer_admins_txt()
    ahora = datetime.now().isoformat(timespec="seconds")

    for usuario in usuarios:
        password_hash = _hash_password("cambiar")
        cursor.execute(
            """
            INSERT OR IGNORE INTO empleados (
                username, nombre, password_hash, activo, is_admin,
                fecha_alta, password_change_required
            )
            VALUES (?, ?, ?, 1, ?, ?, 1)
            """,
            (
                usuario,
                usuario,
                password_hash,
                1 if usuario in admins_txt else 0,
                ahora,
            ),
        )


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jornadas (
            id INTEGER PRIMARY KEY,
            fecha DATE,
            usuario TEXT,
            inicio DATETIME,
            fin DATETIME
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pausas (
            id INTEGER PRIMARY KEY,
            jornada_id INTEGER,
            inicio DATETIME,
            fin DATETIME
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1,
            is_admin INTEGER NOT NULL DEFAULT 0,
            fecha_alta TEXT NOT NULL,
            password_change_required INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Migración suave: si la tabla `empleados` acaba de crearse y ya había
    # jornadas registradas, sembramos empleados con contraseña temporal.
    if _tabla_empleados_esta_vacia(cursor):
        _migrar_empleados_desde_datos_existentes(cursor)

    conn.commit()
    conn.close()


def get_today_jornada(usuario):
    conn = get_connection()
    cursor = conn.cursor()

    fecha_hoy = datetime.now().date()

    cursor.execute("""
        SELECT id, inicio, fin
        FROM jornadas
        WHERE fecha = ? AND usuario = ?
    """, (fecha_hoy, usuario))

    jornada = cursor.fetchone()

    conn.close()

    return jornada


def create_jornada(usuario):

    conn = get_connection()
    cursor = conn.cursor()

    ahora = datetime.now()
    fecha_hoy = ahora.date()

    cursor.execute("""
        INSERT INTO jornadas (fecha, usuario, inicio)
        VALUES (?, ?, ?)
    """, (fecha_hoy, usuario, ahora))

    conn.commit()

    conn.close()

    print(f"Jornada creada a las {ahora}")

def show_jornadas():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM jornadas")

    rows = cursor.fetchall()

    for row in rows:
        print(row)

    conn.close()

#Crear pausa
def iniciar_pausa(jornada_id):

    conn = get_connection()
    cursor = conn.cursor()

    # 🚨 PROTECCIÓN ABSOLUTA
    cursor.execute("""
        SELECT 1 FROM pausas
        WHERE jornada_id = ?
        AND fin IS NULL
    """, (jornada_id,))

    if cursor.fetchone():
        print("ERROR: ya existe una pausa activa")
        conn.close()
        return

    ahora = datetime.now()

    cursor.execute("""
        INSERT INTO pausas (jornada_id, inicio)
        VALUES (?, ?)
    """, (jornada_id, ahora))

    conn.commit()
    conn.close()

    print("Pausa iniciada correctamente")


def obtener_pausa_activa(jornada_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM pausas
        WHERE jornada_id = ?
        AND fin IS NULL
        ORDER BY inicio DESC
        LIMIT 1
    """, (jornada_id,))

    return cursor.fetchone()

def finalizar_pausa(pausa_id):

    conn = get_connection()
    cursor = conn.cursor()

    ahora = datetime.now()

    cursor.execute("""
        UPDATE pausas
        SET fin = ?
        WHERE id = ?
    """, (ahora, pausa_id))

    conn.commit()
    conn.close()

    print(f"Pausa terminada: {ahora}")

#Mostrar pausas
#def show_pausas():
#    conn = get_connection()
#    cursor = conn.cursor()
#    cursor.execute("SELECT * FROM pausas")
#    rows = cursor.fetchall()
#    for row in rows:
#        print(row)
#    conn.close()

#Mostrar jornadas
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pausas")

    rows = cursor.fetchall()

    for row in rows:
        print(row)

    conn.close()


from datetime import datetime


def calcular_segundos_trabajados(jornada_id):

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Obtener jornada (inicio y fin)
    cursor.execute("""
        SELECT inicio, fin
        FROM jornadas
        WHERE id = ?
    """, (jornada_id,))

    inicio, fin = cursor.fetchone()

    inicio = datetime.fromisoformat(inicio)
    # Si la jornada está cerrada usamos su fin; si no, "ahora".
    fin_dt = datetime.fromisoformat(fin) if fin else datetime.now()

    # 2. Tiempo total bruto
    total = (fin_dt - inicio).total_seconds()

    conn.close()

    # 3. Restar pausas
    return total - calcular_segundos_pausas(jornada_id)


def calcular_segundos_pausas(jornada_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT inicio, fin
        FROM pausas
        WHERE jornada_id = ?
    """, (jornada_id,))

    pausas = cursor.fetchall()

    conn.close()

    ahora = datetime.now()
    total_pausas = 0

    for p_inicio, p_fin in pausas:
        p_inicio = datetime.fromisoformat(p_inicio)
        # Pausa aún abierta => cuenta hasta "ahora"
        p_fin = datetime.fromisoformat(p_fin) if p_fin else ahora

        total_pausas += (p_fin - p_inicio).total_seconds()

    return total_pausas

def format_time(seconds):

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


#Finalizar jornada
def finalizar_jornada(jornada_id):

    conn = get_connection()
    cursor = conn.cursor()

    ahora = datetime.now()

    # cerrar cualquier pausa que siga abierta
    cursor.execute("""
        UPDATE pausas
        SET fin = ?
        WHERE jornada_id = ? AND fin IS NULL
    """, (ahora, jornada_id))

    # cerrar jornada
    cursor.execute("""
        UPDATE jornadas
        SET fin = ?
        WHERE id = ?
    """, (ahora, jornada_id))

    conn.commit()
    conn.close()

    print("Jornada finalizada:", ahora)

def cerrar_jornadas_huerfanas(usuario):
    """
    Cierra las jornadas de <usuario> que quedaron abiertas en d\u00edas anteriores
    (por cierre inesperado, apagado, etc.).
    Como `fin` usa la \u00faltima actividad conocida: max(inicio_jornada, ultima_pausa).
    Devuelve el n\u00famero de jornadas cerradas.
    """
    conn = get_connection()
    cursor = conn.cursor()

    hoy = datetime.now().date()

    cursor.execute("""
        SELECT id, inicio
        FROM jornadas
        WHERE usuario = ? AND fin IS NULL AND fecha < ?
    """, (usuario, hoy))

    huerfanas = cursor.fetchall()

    for jornada_id, inicio in huerfanas:

        # Ultima actividad conocida: la pausa m\u00e1s reciente (inicio o fin), o el inicio de la jornada.
        cursor.execute("""
            SELECT MAX(COALESCE(fin, inicio)) FROM pausas WHERE jornada_id = ?
        """, (jornada_id,))
        ultima_pausa = cursor.fetchone()[0]

        candidatos = [datetime.fromisoformat(inicio)]
        if ultima_pausa:
            candidatos.append(datetime.fromisoformat(ultima_pausa))

        fin = max(candidatos)

        # Cerramos tambi\u00e9n cualquier pausa abierta de esa jornada.
        cursor.execute("""
            UPDATE pausas SET fin = ? WHERE jornada_id = ? AND fin IS NULL
        """, (fin, jornada_id))

        cursor.execute("""
            UPDATE jornadas SET fin = ? WHERE id = ?
        """, (fin, jornada_id))

    conn.commit()
    conn.close()

    if huerfanas:
        print(f"Cerradas {len(huerfanas)} jornada(s) hu\u00e9rfana(s).")

    return len(huerfanas)


def reanudar_jornada(jornada_id):
    """
    Reabre una jornada cerrada. Para que el rato entre el cierre y ahora
    no cuente como trabajado, se inserta una pausa que cubre ese hueco.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT fin FROM jornadas WHERE id = ?", (jornada_id,))
    row = cursor.fetchone()

    if not row or row[0] is None:
        conn.close()
        return  # ya está abierta, nada que hacer

    fin_previo = row[0]
    ahora = datetime.now()

    # Pausa que cubre el hueco cerrada->ahora
    cursor.execute("""
        INSERT INTO pausas (jornada_id, inicio, fin)
        VALUES (?, ?, ?)
    """, (jornada_id, fin_previo, ahora))

    # Reabrir la jornada
    cursor.execute("UPDATE jornadas SET fin = NULL WHERE id = ?", (jornada_id,))

    conn.commit()
    conn.close()

    print("Jornada reanudada. Pausa insertada de", fin_previo, "a", ahora)


def jornada_abierta(jornada_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT fin
        FROM jornadas
        WHERE id = ?
    """, (jornada_id,))

    fin = cursor.fetchone()[0]

    conn.close()

    return fin is None


def obtener_jornadas_semana(usuario):

    conn = get_connection()
    cursor = conn.cursor()

    hoy = datetime.now().date()
    inicio_semana = hoy - timedelta(days=hoy.weekday())  # lunes

    cursor.execute("""
        SELECT id, fecha, inicio, fin
        FROM jornadas
        WHERE usuario = ?
        AND fecha >= ?
    """, (usuario, inicio_semana))

    data = cursor.fetchall()

    conn.close()

    return data

def calcular_horas_semana(jornadas):

    total_segundos = 0

    for j in jornadas:

        jornada_id = j[0]

        total_segundos += calcular_segundos_trabajados(jornada_id)

    return total_segundos / 3600


def desglose_horas_semana(jornadas):
    """
    Devuelve dict con 'total', 'normales' y 'extra' (en horas).
    Normales est\u00e1n limitadas por HORAS_SEMANA_ESTANDAR; extra es el excedente.
    """
    total = calcular_horas_semana(jornadas)
    normales = min(total, HORAS_SEMANA_ESTANDAR)
    extra = max(0.0, total - HORAS_SEMANA_ESTANDAR)
    return {
        "total": total,
        "normales": normales,
        "extra": extra,
    }


def desglose_por_semanas_mes(usuario):
    """
    Trocea el mes actual en sus semanas ISO (lunes-domingo) y devuelve una
    lista con el desglose de cada una. Ejemplo:
      [
        {label, lunes, domingo, normales, extra, total},
        ...
      ]
    Se incluyen tambi\u00e9n las semanas sin actividad (con 0 horas), para que
    el gr\u00e1fico tenga ejes coherentes de principio a fin de mes.
    """
    from itertools import groupby

    hoy = datetime.now().date()
    inicio_mes = hoy.replace(day=1)

    # \u00daltimo d\u00eda del mes
    if inicio_mes.month == 12:
        siguiente_mes = date(inicio_mes.year + 1, 1, 1)
    else:
        siguiente_mes = date(inicio_mes.year, inicio_mes.month + 1, 1)
    ultimo_dia = siguiente_mes - timedelta(days=1)

    # Lista de "lunes" a lo largo del mes (semanas ISO que tocan el mes)
    lunes_iter = inicio_mes - timedelta(days=inicio_mes.weekday())
    semanas = []
    while lunes_iter <= ultimo_dia:
        semanas.append(lunes_iter)
        lunes_iter = lunes_iter + timedelta(days=7)

    # Agrupamos las jornadas del mes por lunes de su semana.
    jornadas = obtener_jornadas_mes(usuario)

    def lunes_de(fecha_str):
        d = date.fromisoformat(fecha_str)
        return d - timedelta(days=d.weekday())

    por_semana = {}
    for lunes, grupo in groupby(jornadas, key=lambda j: lunes_de(j[1])):
        por_semana[lunes] = list(grupo)

    resultado = []
    for i, lunes in enumerate(semanas, start=1):
        domingo = lunes + timedelta(days=6)
        js = por_semana.get(lunes, [])
        d = desglose_horas_semana(js) if js else {"total": 0, "normales": 0, "extra": 0}
        resultado.append({
            "label": f"Sem {i}",
            "lunes": lunes,
            "domingo": domingo,
            "normales": d["normales"],
            "extra": d["extra"],
            "total": d["total"],
        })
    return resultado


def obtener_jornadas_mes(usuario):
    """Todas las jornadas del mes actual, ordenadas."""
    conn = get_connection()
    cursor = conn.cursor()

    hoy = datetime.now().date()
    inicio_mes = hoy.replace(day=1)

    cursor.execute("""
        SELECT id, fecha, inicio, fin
        FROM jornadas
        WHERE usuario = ? AND fecha >= ?
        ORDER BY fecha, inicio
    """, (usuario, inicio_mes))

    data = cursor.fetchall()
    conn.close()
    return data


def desglose_mes(usuario):
    """
    Estad\u00edsticas del mes actual para <usuario>. Devuelve dict:
      dias_trabajados, horas_totales, horas_normales, horas_extra,
      num_pausas, tiempo_pausas_h, promedio_horas_dia.
    Las horas extra se calculan agrupando por semana ISO.
    """
    jornadas = obtener_jornadas_mes(usuario)

    if not jornadas:
        return {
            "dias_trabajados": 0,
            "horas_totales": 0.0,
            "horas_normales": 0.0,
            "horas_extra": 0.0,
            "num_pausas": 0,
            "tiempo_pausas_h": 0.0,
            "promedio_horas_dia": 0.0,
        }

    # 1. Horas trabajadas + pausas por jornada
    total_segundos = 0
    total_pausas_segundos = 0
    for jornada_id, *_ in jornadas:
        total_segundos += calcular_segundos_trabajados(jornada_id)
        total_pausas_segundos += calcular_segundos_pausas(jornada_id)

    # 2. Recuento de pausas (una \u00fanica query)
    conn = get_connection()
    cursor = conn.cursor()
    ids = [j[0] for j in jornadas]
    placeholders = ",".join("?" * len(ids))
    cursor.execute(
        f"SELECT COUNT(*) FROM pausas WHERE jornada_id IN ({placeholders})",
        ids,
    )
    num_pausas = cursor.fetchone()[0]
    conn.close()

    # 3. Reparto normales / extra agrupando por semana ISO (lunes)
    from itertools import groupby

    def lunes_de(fecha_str):
        d = date.fromisoformat(fecha_str)
        return d - timedelta(days=d.weekday())

    horas_normales = 0.0
    horas_extra = 0.0
    for _, grupo in groupby(jornadas, key=lambda j: lunes_de(j[1])):
        d = desglose_horas_semana(list(grupo))
        horas_normales += d["normales"]
        horas_extra += d["extra"]

    dias_unicos = len({j[1] for j in jornadas})
    horas_totales = total_segundos / 3600

    return {
        "dias_trabajados": dias_unicos,
        "horas_totales": horas_totales,
        "horas_normales": horas_normales,
        "horas_extra": horas_extra,
        "num_pausas": num_pausas,
        "tiempo_pausas_h": total_pausas_segundos / 3600,
        "promedio_horas_dia": (
            horas_totales / dias_unicos if dias_unicos else 0.0
        ),
    }


def _dataframe_semana(jornadas):
    """
    Construye el DataFrame con el detalle de una semana + fila TOTAL,
    y devuelve tambi\u00e9n un dict con los sumatorios para la hoja Resumen.
    """
    import pandas as pd

    tope = HORAS_SEMANA_ESTANDAR

    # Cronol\u00f3gicamente, para acumular horas correctamente.
    jornadas_ordenadas = sorted(jornadas, key=lambda j: (j[1], j[2]))

    data = []
    acumulado = 0.0

    total_trabajado_s = 0
    total_pausas_s = 0
    total_normales = 0.0
    total_extra = 0.0

    for jornada_id, fecha, inicio, fin in jornadas_ordenadas:

        entrada = datetime.fromisoformat(inicio).strftime("%H:%M:%S")
        salida = (
            datetime.fromisoformat(fin).strftime("%H:%M:%S")
            if fin else "En curso"
        )

        segundos_trabajados = calcular_segundos_trabajados(jornada_id)
        segundos_pausas = calcular_segundos_pausas(jornada_id)
        horas_dia = segundos_trabajados / 3600

        # Reparto entre normales y extra seg\u00fan el acumulado semanal.
        if acumulado >= tope:
            h_normales, h_extra = 0.0, horas_dia
        elif acumulado + horas_dia <= tope:
            h_normales, h_extra = horas_dia, 0.0
        else:
            h_normales = tope - acumulado
            h_extra = horas_dia - h_normales

        acumulado += horas_dia
        total_trabajado_s += segundos_trabajados
        total_pausas_s += segundos_pausas
        total_normales += h_normales
        total_extra += h_extra

        data.append([
            fecha,
            entrada,
            salida,
            format_time(segundos_trabajados),
            format_time(segundos_pausas),
            round(horas_dia, 2),
            round(h_normales, 2),
            round(h_extra, 2),
        ])

    # Fila TOTAL
    data.append([
        "TOTAL",
        "",
        "",
        format_time(total_trabajado_s),
        format_time(total_pausas_s),
        round(total_trabajado_s / 3600, 2),
        round(total_normales, 2),
        round(total_extra, 2),
    ])

    df = pd.DataFrame(data, columns=[
        "Fecha",
        "Entrada",
        "Salida",
        "Horas trabajadas",
        "Tiempo pausas",
        "Horas (decimal)",
        "Horas normales",
        "Horas extra",
    ])

    totales = {
        "total": round(total_trabajado_s / 3600, 2),
        "normales": round(total_normales, 2),
        "extra": round(total_extra, 2),
        # Segundos brutos para poder acumular a nivel mes sin recalcular.
        "trabajado_s": total_trabajado_s,
        "pausas_s": total_pausas_s,
    }
    return df, totales


def exportar_semana_excel(usuario, jornadas, filename=None):
    """
    Escribe un .xlsx (una sola hoja) con las jornadas de la semana
    de <usuario>. Ver columnas en _dataframe_semana.
    Devuelve la ruta del fichero generado.
    """
    df, _ = _dataframe_semana(jornadas)

    if filename is None:
        filename = f"reporte_semana_{usuario}.xlsx"

    df.to_excel(filename, index=False)
    return filename


def obtener_todos_los_usuarios():
    """Devuelve la lista de usuarios distintos que tienen jornadas registradas."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT usuario FROM jornadas ORDER BY usuario")
    usuarios = [row[0] for row in cursor.fetchall()]
    conn.close()
    return usuarios


def exportar_todos_empleados_excel(filename=None):
    """
    Un solo .xlsx con:
      - Hoja 'Resumen': una fila por empleado con total, normales y extra.
      - Una hoja por empleado que tenga jornadas esta semana, con el detalle.
    Devuelve la ruta del fichero generado.
    """
    import pandas as pd

    usuarios = obtener_todos_los_usuarios()

    resumen = []
    hojas = []  # (sheet_name, df) a escribir despu\u00e9s del Resumen

    for usuario in usuarios:
        jornadas = obtener_jornadas_semana(usuario)
        df, tot = _dataframe_semana(jornadas)
        resumen.append([usuario, tot["total"], tot["normales"], tot["extra"]])

        if jornadas:
            # Excel limita nombres de hoja a 31 chars.
            sheet_name = usuario[:31]
            hojas.append((sheet_name, df))

    df_resumen = pd.DataFrame(resumen, columns=[
        "Usuario",
        "Total horas",
        "Horas normales",
        "Horas extra",
    ])

    if filename is None:
        filename = "reporte_semana_TODOS.xlsx"

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df_resumen.to_excel(writer, sheet_name="Resumen", index=False)
        for sheet_name, df in hojas:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    return filename


# ---------------------------------------------------------------------------
# Export MENSUAL
# ---------------------------------------------------------------------------

_COLUMNAS_DETALLE = [
    "Fecha",
    "Entrada",
    "Salida",
    "Horas trabajadas",
    "Tiempo pausas",
    "Horas (decimal)",
    "Horas normales",
    "Horas extra",
]


def _dataframe_mes(jornadas):
    """
    Construye el DataFrame con el detalle de un MES entero:
      - Bloque por cada semana ISO (lunes-domingo), reutilizando la l\u00f3gica
        de `_dataframe_semana`, con su fila TOTAL renombrada a
        "SUBTOTAL Sem N (dd/mm \u2192 dd/mm)".
      - Fila final "TOTAL MES" con los sumatorios del mes.
    El tope de 40h se aplica por CADA semana (se reinicia el acumulado
    cada lunes), no en bloque mensual.
    Devuelve (df, totales_dict).
    """
    import pandas as pd
    from itertools import groupby

    if not jornadas:
        return (
            pd.DataFrame(columns=_COLUMNAS_DETALLE),
            {"total": 0.0, "normales": 0.0, "extra": 0.0},
        )

    jornadas_ordenadas = sorted(jornadas, key=lambda j: (j[1], j[2]))

    def lunes_de(fecha_str):
        d = date.fromisoformat(fecha_str)
        return d - timedelta(days=d.weekday())

    bloques = []
    total_trabajado_s = 0
    total_pausas_s = 0
    total_normales = 0.0
    total_extra = 0.0

    numero_semana = 0
    for lunes, grupo in groupby(jornadas_ordenadas, key=lambda j: lunes_de(j[1])):
        numero_semana += 1
        semana_jornadas = list(grupo)

        df_sem, tot_sem = _dataframe_semana(semana_jornadas)

        # Renombrar la fila TOTAL de la semana como SUBTOTAL con su rango.
        domingo = lunes + timedelta(days=6)
        etiqueta = (
            f"SUBTOTAL Sem {numero_semana} "
            f"({lunes.strftime('%d/%m')} \u2192 {domingo.strftime('%d/%m')})"
        )
        df_sem.iloc[-1, 0] = etiqueta
        bloques.append(df_sem)

        total_normales += tot_sem["normales"]
        total_extra += tot_sem["extra"]
        total_trabajado_s += tot_sem["trabajado_s"]
        total_pausas_s += tot_sem["pausas_s"]

    df = pd.concat(bloques, ignore_index=True)

    # Fila TOTAL MES
    df.loc[len(df)] = [
        "TOTAL MES",
        "",
        "",
        format_time(total_trabajado_s),
        format_time(total_pausas_s),
        round(total_trabajado_s / 3600, 2),
        round(total_normales, 2),
        round(total_extra, 2),
    ]

    totales = {
        "total": round(total_trabajado_s / 3600, 2),
        "normales": round(total_normales, 2),
        "extra": round(total_extra, 2),
    }
    return df, totales


def _sufijo_mes_actual():
    """Devuelve 'YYYY-MM' del mes actual, para nombres de fichero."""
    return datetime.now().strftime("%Y-%m")


def exportar_mes_excel(usuario, jornadas=None, filename=None):
    """
    Escribe un .xlsx (una sola hoja) con todas las jornadas del mes actual
    de <usuario>, con subtotales semanales y un TOTAL MES.
    Devuelve la ruta del fichero generado.
    """
    if jornadas is None:
        jornadas = obtener_jornadas_mes(usuario)

    df, _ = _dataframe_mes(jornadas)

    if filename is None:
        filename = f"reporte_mes_{_sufijo_mes_actual()}_{usuario}.xlsx"

    df.to_excel(filename, index=False)
    return filename


def exportar_todos_empleados_mes_excel(filename=None):
    """
    Un solo .xlsx con:
      - Hoja 'Resumen': una fila por empleado con total, normales y extra
        del MES actual.
      - Una hoja por empleado que tenga jornadas este mes, con el detalle
        (subtotales por semana + TOTAL MES).
    Devuelve la ruta del fichero generado.
    """
    import pandas as pd

    usuarios = obtener_todos_los_usuarios()

    resumen = []
    hojas = []  # (sheet_name, df) a escribir despu\u00e9s del Resumen

    for usuario in usuarios:
        jornadas = obtener_jornadas_mes(usuario)
        df, tot = _dataframe_mes(jornadas)
        resumen.append([usuario, tot["total"], tot["normales"], tot["extra"]])

        if jornadas:
            # Excel limita nombres de hoja a 31 chars.
            sheet_name = usuario[:31]
            hojas.append((sheet_name, df))

    df_resumen = pd.DataFrame(resumen, columns=[
        "Usuario",
        "Total horas",
        "Horas normales",
        "Horas extra",
    ])

    if filename is None:
        filename = f"reporte_mes_{_sufijo_mes_actual()}_TODOS.xlsx"

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df_resumen.to_excel(writer, sheet_name="Resumen", index=False)
        for sheet_name, df in hojas:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    return filename