import os
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QMessageBox, QGroupBox,
    QSystemTrayIcon, QMenu, QStyle,
)
from PySide6.QtGui import QAction, QIcon, QPalette
from PySide6.QtCore import QTimer, Qt

# Chart embebido con matplotlib.
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

TRAY_ICON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "clock.png"
)

from data import (
    get_today_jornada,
    iniciar_pausa,
    obtener_pausa_activa,
    finalizar_pausa,
    finalizar_jornada as db_finalizar_jornada,
    reanudar_jornada as db_reanudar_jornada,
    jornada_abierta,
    calcular_segundos_trabajados,
    format_time,
    obtener_jornadas_semana,
    desglose_horas_semana,
    desglose_mes,
    desglose_por_semanas_mes,
    HORAS_SEMANA_ESTANDAR,
    exportar_todos_empleados_mes_excel,
)
from auth_ui import EmpleadosDialog


# ----------------------------------------------------------------------------
# Estilos (se adaptan a light/dark del sistema usando palette() donde procede).
# ----------------------------------------------------------------------------
STYLE_SHEET = """
QWidget {
    font-family: -apple-system, "SF Pro Text", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid palette(mid);
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
}
QLabel {
    padding: 1px 0;
}
QLabel#label_tiempo {
    font-size: 22px;
    font-weight: bold;
    padding: 6px 0;
}
QLabel#label_semana {
    font-size: 13px;
    padding: 4px 0;
}
QLabel[metrica="valor"] {
    font-weight: 600;
    padding-left: 8px;
}
QPushButton {
    padding: 8px 14px;
    border-radius: 6px;
    min-height: 24px;
}
QPushButton#btn_finalizar {
    background: #e07b00;
    color: white;
    border: none;
    font-weight: 600;
}
QPushButton#btn_finalizar:hover:!disabled {
    background: #ff8f14;
}
QPushButton#btn_finalizar:disabled {
    background: palette(mid);
    color: palette(midlight);
}
QPushButton#btn_reanudar {
    background: #3d8bfd;
    color: white;
    border: none;
    font-weight: 600;
}
QPushButton#btn_reanudar:hover:!disabled {
    background: #5aa0ff;
}
"""


class WeekChartCanvas(FigureCanvasQTAgg):
    """
    Gr\u00e1fico de barras apiladas (normales + extra) por semana del mes,
    con l\u00ednea horizontal en el tope semanal.
    Se adapta al tema (light/dark) del sistema.
    """

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 2.6), tight_layout=True)
        # Fondo transparente para que se vea el fondo del widget de Qt.
        self.fig.patch.set_alpha(0)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setStyleSheet("background: transparent;")

        self.ax = self.fig.add_subplot(111)
        self.ax.patch.set_alpha(0)

        self._text_color = "#333333"
        self._grid_color = "#cccccc"

    def apply_theme(self, is_dark):
        self._text_color = "#e6e6e6" if is_dark else "#333333"
        self._grid_color = "#3a3a3a" if is_dark else "#cccccc"

    def plot(self, semanas, tope):

        self.ax.clear()

        labels = [s["label"] for s in semanas]
        normales = [s["normales"] for s in semanas]
        extras = [s["extra"] for s in semanas]
        x = list(range(len(labels)))

        self.ax.bar(x, normales, color="#3d8bfd", label="Normales", width=0.62)
        self.ax.bar(x, extras, bottom=normales, color="#e07b00",
                    label="Extra", width=0.62)

        # Etiquetas de total encima de cada barra
        for xi, (n, e) in enumerate(zip(normales, extras)):
            total = n + e
            if total > 0:
                self.ax.text(
                    xi, total + max(1, tope * 0.02),
                    f"{total:.1f}h",
                    ha="center", va="bottom",
                    color=self._text_color, fontsize=8,
                )

        # L\u00ednea horizontal del tope
        self.ax.axhline(
            y=tope, color="#888888", linestyle="--", linewidth=0.9,
            label=f"Tope {tope}h",
        )

        # Estilos
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels, color=self._text_color)
        self.ax.tick_params(axis="y", colors=self._text_color)
        self.ax.tick_params(axis="x", colors=self._text_color)
        self.ax.set_ylabel("Horas", color=self._text_color)

        for spine in ("top", "right"):
            self.ax.spines[spine].set_visible(False)
        for spine in ("bottom", "left"):
            self.ax.spines[spine].set_color(self._grid_color)

        self.ax.grid(axis="y", alpha=0.5, color=self._grid_color, linewidth=0.5)
        self.ax.set_axisbelow(True)

        # Espacio para etiquetas encima
        ymax = max([tope] + [n + e for n, e in zip(normales, extras)])
        self.ax.set_ylim(0, ymax * 1.15)

        legend = self.ax.legend(loc="upper right", fontsize=8, frameon=False)
        for txt in legend.get_texts():
            txt.set_color(self._text_color)

        self.draw()


class TimeTrackerApp(QWidget):

    def __init__(self, empleado):
        super().__init__()

        self.setWindowTitle("Time Tracker")
        self.setMinimumSize(300, 200)

        # `empleado` es el dict devuelto por autenticar() en el flujo de login.
        self.empleado = empleado
        self.usuario = empleado["username"]
        self.nombre = empleado["nombre"]
        # Rol: sólo los admins pueden exportar Excel y gestionar empleados.
        # Los empleados normales no verán esos botones.
        self.is_admin = empleado["is_admin"]
        self.jornada = get_today_jornada(self.usuario)

        if not self.jornada:
            raise Exception("No hay jornada activa")

        self.jornada_id = self.jornada[0]

        # Flag para distinguir "cerrar ventana" (minimiza a tray) de
        # "salir de verdad" (men\u00fa del tray \u2192 Salir).
        self._really_quit = False

        self.init_ui()
        self.create_tray_icon()
        self.refresh_state()

    def init_ui(self):

        self.setMinimumWidth(360)

        root = QVBoxLayout()
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # -------- Card: Jornada actual --------
        card_jornada = QGroupBox("Jornada actual")
        grid_j = QGridLayout()
        grid_j.setColumnStretch(1, 1)

        hora_inicio = datetime.fromisoformat(self.jornada[1]).strftime("%H:%M:%S")

        self.label_estado = QLabel("")
        self.label_tiempo = QLabel("00:00:00")
        self.label_tiempo.setObjectName("label_tiempo")
        self.label_tiempo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.label_resumen = QLabel("0.00h")
        self.label_resumen.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        grid_j.addWidget(QLabel("Empleado"), 0, 0)
        etiqueta_empleado = self._val(f"{self.nombre}  ({self.usuario})")
        grid_j.addWidget(etiqueta_empleado, 0, 1)
        grid_j.addWidget(QLabel("Inicio"), 1, 0)
        grid_j.addWidget(self._val(hora_inicio), 1, 1)
        grid_j.addWidget(QLabel("Estado"), 2, 0)
        grid_j.addWidget(self.label_estado, 2, 1)
        grid_j.addWidget(QLabel("Tiempo trabajado"), 3, 0)
        grid_j.addWidget(self.label_tiempo, 3, 1)
        grid_j.addWidget(QLabel("Horas hoy"), 4, 0)
        grid_j.addWidget(self.label_resumen, 4, 1)

        card_jornada.setLayout(grid_j)

        # -------- Card: Semana --------
        card_semana = QGroupBox("Esta semana")
        vs = QVBoxLayout()
        self.label_semana = QLabel("Horas esta semana: 0.00h")
        self.label_semana.setObjectName("label_semana")
        vs.addWidget(self.label_semana)
        card_semana.setLayout(vs)

        # -------- Botones acci\u00f3n --------
        self.btn_pausa = QPushButton("Iniciar pausa")
        self.btn_finalizar = QPushButton("Finalizar jornada")
        self.btn_finalizar.setObjectName("btn_finalizar")
        self.btn_reanudar = QPushButton("Reanudar jornada")
        self.btn_reanudar.setObjectName("btn_reanudar")

        self.btn_pausa.clicked.connect(self.toggle_pausa)
        self.btn_finalizar.clicked.connect(self.finalizar_jornada)
        self.btn_reanudar.clicked.connect(self.reanudar_jornada)

        row_botones = QHBoxLayout()
        row_botones.addWidget(self.btn_pausa)
        row_botones.addWidget(self.btn_finalizar)
        row_botones.addWidget(self.btn_reanudar)

        # -------- Botones de admin --------
        # Los empleados normales no ven estos botones para evitar que puedan
        # descargar el Excel/editar empleados. Sólo los usuarios marcados
        # como admin en la tabla `empleados` tienen acceso.
        # El reporte es MENSUAL y consolidado: incluye a TODOS los empleados
        # en un único fichero, se descarga una vez al mes.
        row_export = None
        if self.is_admin:
            self.btn_export_all = QPushButton("Exportar reporte mensual (todos)")
            self.btn_export_all.clicked.connect(self.export_all_month)

            self.btn_empleados = QPushButton("Gestión de empleados…")
            self.btn_empleados.clicked.connect(self.abrir_panel_empleados)

            row_export = QHBoxLayout()
            row_export.addWidget(self.btn_empleados)
            row_export.addWidget(self.btn_export_all)

        # -------- Card: Rendimiento del mes (oculto por defecto,
        # aparece al finalizar la jornada) --------
        self.card_mes = QGroupBox("Rendimiento del mes")
        v_mes = QVBoxLayout()
        v_mes.setSpacing(8)

        # Fila superior: m\u00e9tricas resumen en dos columnas.
        grid_m = QGridLayout()
        grid_m.setColumnStretch(1, 1)
        grid_m.setColumnStretch(3, 1)

        self.lbl_mes_dias = self._val("\u2014")
        self.lbl_mes_total = self._val("\u2014")
        self.lbl_mes_normales = self._val("\u2014")
        self.lbl_mes_extra = self._val("\u2014")
        self.lbl_mes_pausas = self._val("\u2014")
        self.lbl_mes_media = self._val("\u2014")

        # (fila, col_label, col_val, etiqueta, widget)
        metricas = [
            (0, 0, 1, "D\u00edas trabajados", self.lbl_mes_dias),
            (0, 2, 3, "Horas totales", self.lbl_mes_total),
            (1, 0, 1, "Horas normales", self.lbl_mes_normales),
            (1, 2, 3, "Horas extra", self.lbl_mes_extra),
            (2, 0, 1, "Pausas tomadas", self.lbl_mes_pausas),
            (2, 2, 3, "Media horas/d\u00eda", self.lbl_mes_media),
        ]
        for row, cl, cv, etiqueta, widget in metricas:
            grid_m.addWidget(QLabel(etiqueta), row, cl)
            grid_m.addWidget(widget, row, cv)

        v_mes.addLayout(grid_m)

        # Chart de barras por semana.
        self.chart_semanas = WeekChartCanvas(self)
        self.chart_semanas.setMinimumHeight(220)
        v_mes.addWidget(self.chart_semanas)

        self.card_mes.setLayout(v_mes)
        self.card_mes.setVisible(False)

        # -------- Ensamblado --------
        root.addWidget(card_jornada)
        root.addWidget(card_semana)
        root.addLayout(row_botones)
        if row_export is not None:
            root.addLayout(row_export)
        root.addWidget(self.card_mes)
        root.addStretch(1)

        self.setLayout(root)
        self.setStyleSheet(STYLE_SHEET)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)

        # Autosave / heartbeat: cada 30s re-sincroniza estado.
        self.timer_autosave = QTimer()
        self.timer_autosave.timeout.connect(self.check_state)
        self.timer_autosave.start(30_000)

    def _val(self, text):
        """Crea un QLabel con estilo de 'valor' (alineado a la derecha, semi-bold)."""
        lbl = QLabel(text)
        lbl.setProperty("metrica", "valor")
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lbl

    def check_state(self):
        # Re-lee el estado desde la BD y sincroniza la UI.
        self.refresh_state()

    def create_tray_icon(self):

        self.tray = QSystemTrayIcon(self)

        # Si el .png no existiera, usamos un icono est\u00e1ndar de Qt como fallback.
        if os.path.exists(TRAY_ICON_PATH):
            self.tray.setIcon(QIcon(TRAY_ICON_PATH))
        else:
            self.tray.setIcon(
                self.style().standardIcon(QStyle.SP_ComputerIcon)
            )

        self.tray.setToolTip("Time Tracker")

        menu = QMenu()

        mostrar_action = QAction("Mostrar aplicaci\u00f3n", self)
        mostrar_action.triggered.connect(self.show_from_tray)

        pausa_action = QAction("Pausar / Reanudar pausa", self)
        pausa_action.triggered.connect(self.toggle_pausa)

        salir_action = QAction("Salir", self)
        salir_action.triggered.connect(self.quit_app)

        menu.addAction(mostrar_action)
        menu.addSeparator()
        menu.addAction(pausa_action)
        menu.addSeparator()
        menu.addAction(salir_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_clicked)
        self.tray.show()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_from_tray()

    def show_from_tray(self):
        # Trae la ventana al frente aunque estuviera oculta o minimizada.
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        # Salida real: activamos el flag y pedimos cierre a Qt.
        self._really_quit = True
        self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event):
        # Salida real -> aceptamos el cierre.
        if self._really_quit:
            event.accept()
            return

        # Cierre normal (la X) -> ocultamos a la bandeja.
        self.hide()
        self.tray.showMessage(
            "Time Tracker",
            "La aplicaci\u00f3n sigue ejecut\u00e1ndose en segundo plano.",
            QSystemTrayIcon.Information,
            3000,
        )
        event.ignore()

    def _set_estado(self, texto, color):
        self.label_estado.setText(texto)
        self.label_estado.setStyleSheet(f"color: {color}; font-weight: bold;")

    def refresh_state(self):

        # Jornada cerrada: mostramos dashboard mensual + reanudar.
        if not jornada_abierta(self.jornada_id):
            self._set_estado("JORNADA CERRADA", "#c0392b")
            self.btn_pausa.setText("Iniciar pausa")
            self.btn_pausa.setEnabled(False)
            self.btn_finalizar.setEnabled(False)
            self.btn_reanudar.setVisible(True)
            if hasattr(self, "timer"):
                self.update_time()
                self.timer.stop()
            self.update_dashboard_mes()
            self.card_mes.setVisible(True)
            self.adjustSize()
            return

        # Jornada abierta: ocultamos dashboard para ahorrar espacio.
        self.btn_reanudar.setVisible(False)
        self.btn_pausa.setEnabled(True)
        self.btn_finalizar.setEnabled(True)
        self.card_mes.setVisible(False)
        self.adjustSize()

        pausa = obtener_pausa_activa(self.jornada_id)

        if pausa:
            self._set_estado("EN PAUSA", "#e07b00")
            self.btn_pausa.setText("Finalizar pausa")
        else:
            self._set_estado("TRABAJANDO", "#2e8b57")
            self.btn_pausa.setText("Iniciar pausa")

    def toggle_pausa(self):

        pausa = obtener_pausa_activa(self.jornada_id)

        if pausa:
            finalizar_pausa(pausa[0])
        else:
            iniciar_pausa(self.jornada_id)

        self.refresh_state()

    def update_time(self):

        segundos = calcular_segundos_trabajados(self.jornada_id)

        self.label_tiempo.setText(format_time(segundos))
        self.update_resumen()
        self.update_semana()

    def update_resumen(self):

        segundos = calcular_segundos_trabajados(self.jornada_id)
        horas = segundos / 3600
        self.label_resumen.setText(f"{horas:.2f}h")

    def finalizar_jornada(self):

        if jornada_abierta(self.jornada_id):
            db_finalizar_jornada(self.jornada_id)

        # refresh_state congela la UI, para el timer y muestra "Reanudar"
        self.refresh_state()

    def reanudar_jornada(self):

        db_reanudar_jornada(self.jornada_id)

        # La jornada vuelve a estar abierta: reactivamos el timer
        self.timer.start(1000)
        self.refresh_state()
        self.update_time()

    def update_semana(self):

        jornadas = obtener_jornadas_semana(self.usuario)
        desglose = desglose_horas_semana(jornadas)

        if desglose["extra"] > 0:
            texto = (
                f"{desglose['total']:.2f}h  "
                f"({desglose['normales']:.2f}h normales + "
                f"{desglose['extra']:.2f}h extra)"
            )
            self.label_semana.setStyleSheet(
                "color: #e07b00; font-weight: bold; font-size: 14px;"
            )
        else:
            texto = (
                f"{desglose['total']:.2f}h  / {HORAS_SEMANA_ESTANDAR}h"
            )
            self.label_semana.setStyleSheet("font-size: 14px;")

        self.label_semana.setText(texto)

    def update_dashboard_mes(self):
        d = desglose_mes(self.usuario)

        self.lbl_mes_dias.setText(str(d["dias_trabajados"]))
        self.lbl_mes_total.setText(f"{d['horas_totales']:.2f}h")
        self.lbl_mes_normales.setText(f"{d['horas_normales']:.2f}h")

        if d["horas_extra"] > 0:
            self.lbl_mes_extra.setText(f"{d['horas_extra']:.2f}h")
            self.lbl_mes_extra.setStyleSheet(
                "color: #e07b00; font-weight: bold;"
            )
        else:
            self.lbl_mes_extra.setText("0.00h")
            self.lbl_mes_extra.setStyleSheet("")

        self.lbl_mes_pausas.setText(str(d["num_pausas"]))
        self.lbl_mes_media.setText(f"{d['promedio_horas_dia']:.2f}h")

        # Chart de barras por semana
        semanas = desglose_por_semanas_mes(self.usuario)
        # Detecta light/dark segun la paleta actual
        pal = self.palette()
        is_dark = pal.color(QPalette.Window).lightness() < 128
        self.chart_semanas.apply_theme(is_dark)
        self.chart_semanas.plot(semanas, HORAS_SEMANA_ESTANDAR)

    def abrir_panel_empleados(self):

        if not self.is_admin:
            QMessageBox.warning(
                self, "Acceso restringido",
                "Solo un administrador puede gestionar empleados."
            )
            return

        dlg = EmpleadosDialog(self, current_username=self.usuario)
        dlg.exec()

    def export_all_month(self):

        if not self.is_admin:
            QMessageBox.warning(
                self, "Acceso restringido",
                "Solo el administrador puede exportar reportes."
            )
            return

        try:
            filename = exportar_todos_empleados_mes_excel()
        except Exception as e:
            QMessageBox.critical(
                self, "Error exportando",
                f"No se pudo generar el Excel:\n{e}"
            )
            return

        ruta = os.path.abspath(filename)
        print("Exportado (todos, mes):", ruta)
        QMessageBox.information(
            self, "Exportar todos",
            f"Reporte mensual de todos los empleados generado:\n{ruta}"
        )
