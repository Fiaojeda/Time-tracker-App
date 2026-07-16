"""Capa de acceso a datos: local (SQLite) o remota (servidor central).

El resto de la app importa desde aquí en vez de desde `database` /
`api_client` directamente.
"""

from config import is_remote

if is_remote():
    from api_client import (  # noqa: F401
        HORAS_SEMANA_ESTANDAR,
        actualizar_empleado,
        autenticar,
        calcular_segundos_trabajados,
        cambiar_password,
        cerrar_jornadas_huerfanas,
        create_jornada,
        crear_empleado,
        desglose_horas_semana,
        desglose_mes,
        desglose_por_semanas_mes,
        es_admin,
        exportar_todos_empleados_mes_excel,
        finalizar_jornada,
        finalizar_pausa,
        format_time,
        get_today_jornada,
        hay_algun_admin_activo,
        init_db,
        iniciar_pausa,
        jornada_abierta,
        listar_empleados,
        obtener_empleado,
        obtener_jornadas_semana,
        obtener_pausa_activa,
        reanudar_jornada,
    )
else:
    from database import (  # noqa: F401
        HORAS_SEMANA_ESTANDAR,
        actualizar_empleado,
        autenticar,
        calcular_segundos_trabajados,
        cambiar_password,
        cerrar_jornadas_huerfanas,
        create_jornada,
        crear_empleado,
        desglose_horas_semana,
        desglose_mes,
        desglose_por_semanas_mes,
        es_admin,
        exportar_todos_empleados_mes_excel,
        finalizar_jornada,
        finalizar_pausa,
        format_time,
        get_today_jornada,
        hay_algun_admin_activo,
        init_db,
        iniciar_pausa,
        jornada_abierta,
        listar_empleados,
        obtener_empleado,
        obtener_jornadas_semana,
        obtener_pausa_activa,
        reanudar_jornada,
    )
