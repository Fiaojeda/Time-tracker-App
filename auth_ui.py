"""Diálogos de autenticación y gestión de empleados.

Contiene:
    - LoginDialog: pantalla de login (usuario + contraseña).
    - BootstrapAdminDialog: creación del primer admin cuando aún no existe
      ninguno en la base de datos.
    - ChangePasswordDialog: cambio de contraseña (forzado tras primer login
      con contraseña temporal, o voluntario desde el panel admin).
    - EmpleadosDialog: panel para que un admin cree, edite y active/desactive
      empleados.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QVBoxLayout,
    QLabel, QLineEdit, QCheckBox, QPushButton, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from data import (
    autenticar,
    cambiar_password,
    crear_empleado,
    listar_empleados,
    actualizar_empleado,
    obtener_empleado,
)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginDialog(QDialog):
    """Pide usuario y contraseña. Al aceptar, guarda el empleado autenticado."""

    def __init__(self, parent=None, mensaje_inicial=None):
        super().__init__(parent)
        self.setWindowTitle("Iniciar sesión")
        self.setModal(True)
        self.setMinimumWidth(320)

        self.empleado = None  # se rellena al autenticar correctamente

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        titulo = QLabel("Time Tracker")
        titulo.setStyleSheet("font-size: 18px; font-weight: 600;")
        titulo.setAlignment(Qt.AlignCenter)
        root.addWidget(titulo)

        if mensaje_inicial:
            info = QLabel(mensaje_inicial)
            info.setWordWrap(True)
            info.setStyleSheet("color: palette(mid);")
            root.addWidget(info)

        form = QFormLayout()
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("usuario")
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass.setPlaceholderText("contraseña")
        form.addRow("Usuario:", self.input_user)
        form.addRow("Contraseña:", self.input_pass)
        root.addLayout(form)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #c0392b;")
        self.lbl_error.setVisible(False)
        root.addWidget(self.lbl_error)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        botones.button(QDialogButtonBox.Ok).setText("Entrar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self._on_accept)
        botones.rejected.connect(self.reject)
        root.addWidget(botones)

        self.input_pass.returnPressed.connect(self._on_accept)
        self.input_user.returnPressed.connect(
            lambda: self.input_pass.setFocus()
        )

    def _mostrar_error(self, texto):
        self.lbl_error.setText(texto)
        self.lbl_error.setVisible(True)

    def _on_accept(self):
        username = self.input_user.text().strip()
        password = self.input_pass.text()

        if not username or not password:
            self._mostrar_error("Introduce usuario y contraseña.")
            return

        try:
            empleado = autenticar(username, password)
        except ConnectionError as exc:
            self._mostrar_error(str(exc))
            return

        if not empleado:
            self._mostrar_error("Usuario o contraseña incorrectos.")
            self.input_pass.clear()
            self.input_pass.setFocus()
            return

        self.empleado = empleado
        self.accept()


# ---------------------------------------------------------------------------
# Bootstrap del primer admin
# ---------------------------------------------------------------------------

class BootstrapAdminDialog(QDialog):
    """Se muestra cuando no hay ningún admin activo en la BD.

    Fuerza la creación del primer administrador antes de poder usar la app.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crear administrador inicial")
        self.setModal(True)
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        info = QLabel(
            "No hay ningún administrador registrado.\n"
            "Crea el primer usuario administrador para poder usar la aplicación."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        self.input_user = QLineEdit()
        self.input_nombre = QLineEdit()
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass_confirm = QLineEdit()
        self.input_pass_confirm.setEchoMode(QLineEdit.Password)
        form.addRow("Usuario:", self.input_user)
        form.addRow("Nombre:", self.input_nombre)
        form.addRow("Contraseña:", self.input_pass)
        form.addRow("Repetir contraseña:", self.input_pass_confirm)
        root.addLayout(form)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #c0392b;")
        self.lbl_error.setVisible(False)
        root.addWidget(self.lbl_error)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        botones.button(QDialogButtonBox.Ok).setText("Crear")
        botones.accepted.connect(self._on_accept)
        botones.rejected.connect(self.reject)
        root.addWidget(botones)

    def _mostrar_error(self, texto):
        self.lbl_error.setText(texto)
        self.lbl_error.setVisible(True)

    def _on_accept(self):
        username = self.input_user.text().strip()
        nombre = self.input_nombre.text().strip()
        password = self.input_pass.text()
        confirm = self.input_pass_confirm.text()

        if not username or not nombre or not password:
            self._mostrar_error("Rellena todos los campos.")
            return

        if password != confirm:
            self._mostrar_error("Las contraseñas no coinciden.")
            return

        if len(password) < 4:
            self._mostrar_error("La contraseña debe tener al menos 4 caracteres.")
            return

        try:
            crear_empleado(
                username=username,
                nombre=nombre,
                password=password,
                is_admin=True,
                activo=True,
                password_change_required=False,
            )
        except ValueError as e:
            self._mostrar_error(str(e))
            return

        self.accept()


# ---------------------------------------------------------------------------
# Cambio de contraseña
# ---------------------------------------------------------------------------

class ChangePasswordDialog(QDialog):
    """Cambia la contraseña de un usuario ya autenticado.

    Si `forzado=True` se muestra un mensaje explicando que el cambio es
    obligatorio (típico tras primer login con contraseña temporal) y no se
    permite cancelar.
    """

    def __init__(self, username, parent=None, forzado=False):
        super().__init__(parent)
        self.username = username
        self.forzado = forzado
        self.setWindowTitle("Cambiar contraseña")
        self.setModal(True)
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        if forzado:
            info = QLabel(
                "Por seguridad debes establecer una nueva contraseña "
                "antes de continuar."
            )
            info.setWordWrap(True)
            root.addWidget(info)

        form = QFormLayout()
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass_confirm = QLineEdit()
        self.input_pass_confirm.setEchoMode(QLineEdit.Password)
        form.addRow("Nueva contraseña:", self.input_pass)
        form.addRow("Repetir contraseña:", self.input_pass_confirm)
        root.addLayout(form)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #c0392b;")
        self.lbl_error.setVisible(False)
        root.addWidget(self.lbl_error)

        flags = QDialogButtonBox.Ok
        if not forzado:
            flags |= QDialogButtonBox.Cancel
        botones = QDialogButtonBox(flags)
        botones.button(QDialogButtonBox.Ok).setText("Guardar")
        botones.accepted.connect(self._on_accept)
        if not forzado:
            botones.rejected.connect(self.reject)
        root.addWidget(botones)

        # En modo forzado la X no debe cerrar el diálogo.
        if forzado:
            self.setWindowFlags(
                self.windowFlags() & ~Qt.WindowCloseButtonHint
            )

    def _mostrar_error(self, texto):
        self.lbl_error.setText(texto)
        self.lbl_error.setVisible(True)

    def _on_accept(self):
        password = self.input_pass.text()
        confirm = self.input_pass_confirm.text()

        if not password:
            self._mostrar_error("La contraseña no puede estar vacía.")
            return
        if password != confirm:
            self._mostrar_error("Las contraseñas no coinciden.")
            return
        if len(password) < 4:
            self._mostrar_error("La contraseña debe tener al menos 4 caracteres.")
            return

        try:
            cambiar_password(self.username, password)
        except ValueError as e:
            self._mostrar_error(str(e))
            return

        self.accept()


# ---------------------------------------------------------------------------
# Panel de gestión de empleados
# ---------------------------------------------------------------------------

class _AdminResetPasswordDialog(QDialog):
    """Diálogo con el que un admin resetea la contraseña de otro empleado.

    Al guardar, activa `password_change_required` para forzar el cambio de
    contraseña en el próximo login del empleado.
    """

    def __init__(self, target_username, parent=None):
        super().__init__(parent)
        self.target_username = target_username
        self.setWindowTitle(f"Restablecer contraseña de {target_username}")
        self.setModal(True)
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        info = QLabel(
            f"Introduce una contraseña temporal para {target_username}.\n"
            "Se le pedirá que la cambie la próxima vez que inicie sesión."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass_confirm = QLineEdit()
        self.input_pass_confirm.setEchoMode(QLineEdit.Password)
        form.addRow("Contraseña temporal:", self.input_pass)
        form.addRow("Repetir contraseña:", self.input_pass_confirm)
        root.addLayout(form)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #c0392b;")
        self.lbl_error.setVisible(False)
        root.addWidget(self.lbl_error)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        botones.button(QDialogButtonBox.Ok).setText("Restablecer")
        botones.accepted.connect(self._on_accept)
        botones.rejected.connect(self.reject)
        root.addWidget(botones)

    def _mostrar_error(self, texto):
        self.lbl_error.setText(texto)
        self.lbl_error.setVisible(True)

    def _on_accept(self):
        password = self.input_pass.text()
        confirm = self.input_pass_confirm.text()

        if not password:
            self._mostrar_error("La contraseña no puede estar vacía.")
            return
        if password != confirm:
            self._mostrar_error("Las contraseñas no coinciden.")
            return
        if len(password) < 4:
            self._mostrar_error("La contraseña debe tener al menos 4 caracteres.")
            return

        try:
            cambiar_password(
                self.target_username, password, force_change_next_login=True
            )
        except ValueError as e:
            self._mostrar_error(str(e))
            return

        self.accept()


class _EmpleadoFormDialog(QDialog):
    """Diálogo interno para crear o editar un empleado.

    En modo "crear" pide todos los campos + contraseña.
    En modo "editar" oculta usuario y contraseña (readonly), y solo permite
    cambiar nombre, admin y activo.
    """

    def __init__(self, parent=None, empleado=None):
        super().__init__(parent)
        self.empleado = empleado
        self.es_nuevo = empleado is None

        self.setWindowTitle(
            "Nuevo empleado" if self.es_nuevo else f"Editar {empleado['username']}"
        )
        self.setModal(True)
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        form = QFormLayout()

        self.input_user = QLineEdit()
        self.input_nombre = QLineEdit()
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.check_admin = QCheckBox("Es administrador")
        self.check_activo = QCheckBox("Activo")
        self.check_activo.setChecked(True)

        if not self.es_nuevo:
            self.input_user.setText(empleado["username"])
            self.input_user.setReadOnly(True)
            self.input_nombre.setText(empleado["nombre"])
            self.check_admin.setChecked(empleado["is_admin"])
            self.check_activo.setChecked(empleado["activo"])

        form.addRow("Usuario:", self.input_user)
        form.addRow("Nombre:", self.input_nombre)

        if self.es_nuevo:
            form.addRow("Contraseña inicial:", self.input_pass)

        form.addRow("", self.check_admin)
        form.addRow("", self.check_activo)

        root.addLayout(form)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #c0392b;")
        self.lbl_error.setVisible(False)
        root.addWidget(self.lbl_error)

        botones = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        botones.button(QDialogButtonBox.Ok).setText("Guardar")
        botones.accepted.connect(self._on_accept)
        botones.rejected.connect(self.reject)
        root.addWidget(botones)

    def _mostrar_error(self, texto):
        self.lbl_error.setText(texto)
        self.lbl_error.setVisible(True)

    def _on_accept(self):
        nombre = self.input_nombre.text().strip()
        if not nombre:
            self._mostrar_error("El nombre es obligatorio.")
            return

        try:
            if self.es_nuevo:
                username = self.input_user.text().strip()
                password = self.input_pass.text()
                if not username:
                    self._mostrar_error("El usuario es obligatorio.")
                    return
                if not password or len(password) < 4:
                    self._mostrar_error(
                        "La contraseña debe tener al menos 4 caracteres."
                    )
                    return

                crear_empleado(
                    username=username,
                    nombre=nombre,
                    password=password,
                    is_admin=self.check_admin.isChecked(),
                    activo=self.check_activo.isChecked(),
                    password_change_required=True,  # el empleado la cambia al entrar
                )
            else:
                actualizar_empleado(
                    self.empleado["username"],
                    nombre=nombre,
                    is_admin=self.check_admin.isChecked(),
                    activo=self.check_activo.isChecked(),
                )
        except ValueError as e:
            self._mostrar_error(str(e))
            return

        self.accept()


class EmpleadosDialog(QDialog):
    """Panel de administración: lista de empleados con acciones CRUD.

    Solo debe ser abierto por un admin (el llamador es responsable de esa
    comprobación).
    """

    _COLS = ["Usuario", "Nombre", "Admin", "Activo", "Alta"]

    def __init__(self, parent=None, current_username=None):
        super().__init__(parent)
        # current_username: username del admin que está usando el panel, para
        # protegerle de "auto-inhabilitarse" o quitarse el rol admin.
        self.current_username = current_username

        self.setWindowTitle("Gestión de empleados")
        self.setModal(True)
        self.resize(640, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.tabla = QTableWidget(0, len(self._COLS))
        self.tabla.setHorizontalHeaderLabels(self._COLS)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla.verticalHeader().setVisible(False)
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        root.addWidget(self.tabla)

        row_botones = QHBoxLayout()
        self.btn_nuevo = QPushButton("Nuevo…")
        self.btn_editar = QPushButton("Editar…")
        self.btn_password = QPushButton("Restablecer contraseña…")
        self.btn_activar = QPushButton("Activar/Desactivar")
        self.btn_cerrar = QPushButton("Cerrar")

        self.btn_nuevo.clicked.connect(self._nuevo)
        self.btn_editar.clicked.connect(self._editar)
        self.btn_password.clicked.connect(self._reset_password)
        self.btn_activar.clicked.connect(self._toggle_activo)
        self.btn_cerrar.clicked.connect(self.accept)

        row_botones.addWidget(self.btn_nuevo)
        row_botones.addWidget(self.btn_editar)
        row_botones.addWidget(self.btn_password)
        row_botones.addWidget(self.btn_activar)
        row_botones.addStretch(1)
        row_botones.addWidget(self.btn_cerrar)
        root.addLayout(row_botones)

        self._recargar()

    def _empleado_seleccionado(self):
        fila = self.tabla.currentRow()
        if fila < 0:
            return None
        item = self.tabla.item(fila, 0)
        if not item:
            return None
        username = item.data(Qt.UserRole)
        return obtener_empleado(username)

    def _recargar(self):
        empleados = listar_empleados(incluir_inactivos=True)

        self.tabla.setRowCount(len(empleados))
        for i, emp in enumerate(empleados):
            valores = [
                emp["username"],
                emp["nombre"],
                "Sí" if emp["is_admin"] else "",
                "Sí" if emp["activo"] else "No",
                emp["fecha_alta"][:10] if emp["fecha_alta"] else "",
            ]
            for j, valor in enumerate(valores):
                item = QTableWidgetItem(valor)
                if j == 0:
                    # Guardamos el username en el rol UserRole para localizar
                    # de forma robusta el empleado seleccionado.
                    item.setData(Qt.UserRole, emp["username"])
                if not emp["activo"]:
                    item.setForeground(Qt.gray)
                self.tabla.setItem(i, j, item)

    def _nuevo(self):
        dlg = _EmpleadoFormDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._recargar()

    def _editar(self):
        emp = self._empleado_seleccionado()
        if not emp:
            QMessageBox.information(
                self, "Seleccionar empleado",
                "Selecciona primero un empleado de la lista."
            )
            return

        dlg = _EmpleadoFormDialog(self, empleado=emp)
        if dlg.exec() != QDialog.Accepted:
            return

        # Evitar dejar al sistema sin admins (o al admin actual sin permisos).
        if emp["username"] == self.current_username:
            actualizado = obtener_empleado(emp["username"])
            if actualizado and (not actualizado["is_admin"] or not actualizado["activo"]):
                QMessageBox.warning(
                    self, "Cambio no permitido",
                    "No puedes quitarte el rol admin ni darte de baja a ti mismo.\n"
                    "Se han revertido esos cambios."
                )
                actualizar_empleado(
                    emp["username"], is_admin=True, activo=True
                )

        self._recargar()

    def _reset_password(self):
        emp = self._empleado_seleccionado()
        if not emp:
            QMessageBox.information(
                self, "Seleccionar empleado",
                "Selecciona primero un empleado de la lista."
            )
            return

        dlg = _AdminResetPasswordDialog(emp["username"], self)
        if dlg.exec() == QDialog.Accepted:
            QMessageBox.information(
                self, "Contraseña restablecida",
                f"Se le pedirá a {emp['username']} que la cambie en su próximo login."
            )

    def _toggle_activo(self):
        emp = self._empleado_seleccionado()
        if not emp:
            QMessageBox.information(
                self, "Seleccionar empleado",
                "Selecciona primero un empleado de la lista."
            )
            return

        if emp["username"] == self.current_username:
            QMessageBox.warning(
                self, "Acción no permitida",
                "No puedes darte de baja a ti mismo."
            )
            return

        nuevo = not emp["activo"]
        try:
            actualizar_empleado(emp["username"], activo=nuevo)
        except ValueError as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        self._recargar()
