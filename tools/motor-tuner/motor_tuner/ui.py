from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSignalBlocker, QTime, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import dm_motor
from .protocol import (
    CanFrame,
    Command,
    Frame,
    can_tx_frame,
    join_hex,
    ping_frame,
    stream_start_frame,
)
from .transport import SerialTransport, SimulatorTransport, Transport, available_serial_ports

APP_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = APP_DIR / "config.json"

MOTOR_DEFAULTS: list[dict[str, Any]] = [
    {"number": 1, "role": "右侧关节 0", "bus": 0, "control_id": 0x01, "mst_id": 0x11, "direction": 1.0, "torque_limit": 3.0},
    {"number": 2, "role": "右侧轮毂", "bus": 0, "control_id": 0x02, "mst_id": 0x12, "direction": 1.0, "torque_limit": 1.0},
    {"number": 3, "role": "右侧关节 1", "bus": 0, "control_id": 0x03, "mst_id": 0x13, "direction": 1.0, "torque_limit": 3.0},
    {"number": 4, "role": "左侧关节 0", "bus": 1, "control_id": 0x04, "mst_id": 0x14, "direction": 1.0, "torque_limit": 3.0},
    {"number": 5, "role": "左侧轮毂", "bus": 1, "control_id": 0x05, "mst_id": 0x15, "direction": 1.0, "torque_limit": 1.0},
    {"number": 6, "role": "左侧关节 1", "bus": 1, "control_id": 0x06, "mst_id": 0x16, "direction": 1.0, "torque_limit": 3.0},
]


STYLESHEET = """
QMainWindow, QWidget {
    background: #11161e;
    color: #d9e2ec;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 10pt;
}
QGroupBox {
    border: 1px solid #2a3543;
    border-radius: 7px;
    margin-top: 13px;
    padding-top: 9px;
    background: #161d27;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: #8fa8bd;
    font-weight: 600;
}
QLabel#Title {
    font-size: 22pt;
    font-weight: 700;
    color: #f2f6fa;
}
QLabel#Subtitle {
    color: #8799aa;
}
QLabel#RoleLabel {
    color: #5dd6b0;
    font-size: 12pt;
    font-weight: 600;
}
QLabel#StatusOk {
    color: #5dd6b0;
    font-weight: 600;
}
QLabel#StatusOff {
    color: #f07c82;
    font-weight: 600;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #202937;
    border: 1px solid #334255;
    border-radius: 4px;
    padding: 5px 7px;
    selection-background-color: #237a68;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #4fd1b3;
}
QPushButton {
    background: #243342;
    border: 1px solid #384b61;
    border-radius: 5px;
    padding: 7px 13px;
}
QPushButton:hover {
    background: #2f4559;
    border-color: #4a6a86;
}
QPushButton:pressed {
    background: #1c2835;
}
QPushButton#Primary {
    background: #227a68;
    border-color: #2e9e86;
    color: #f7fffd;
    font-weight: 600;
}
QPushButton#Primary:hover {
    background: #2a937d;
}
QPushButton#Danger {
    background: #5a2930;
    border-color: #86424c;
    color: #ffdfe2;
}
QPushButton#Danger:hover {
    background: #71323b;
}
QPushButton#Connect {
    background: #2b5f9f;
    border-color: #3f7cc8;
    color: white;
    font-weight: 600;
    min-width: 88px;
}
QTabWidget::pane {
    border: 1px solid #2a3543;
    border-radius: 6px;
    background: #141b24;
}
QTabBar::tab {
    background: #1a2330;
    color: #91a5b8;
    padding: 9px 17px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #263749;
    color: #8ff0d8;
}
QTableWidget {
    background: #121a23;
    alternate-background-color: #16202b;
    border: 1px solid #2a3543;
    border-radius: 5px;
    gridline-color: #253141;
    selection-background-color: #245b53;
}
QHeaderView::section {
    background: #202b3a;
    color: #9db2c5;
    border: none;
    border-right: 1px solid #2c3a4b;
    padding: 7px;
    font-weight: 600;
}
QSlider::groove:horizontal {
    height: 5px;
    border-radius: 2px;
    background: #2a3543;
}
QSlider::sub-page:horizontal {
    background: #3fc1a4;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 15px;
    height: 15px;
    margin: -5px 0;
    border-radius: 7px;
    background: #e8fffa;
    border: 2px solid #3fc1a4;
}
QScrollBar:vertical {
    width: 10px;
    background: #11161e;
}
QScrollBar::handle:vertical {
    background: #34465a;
    border-radius: 5px;
    min-height: 25px;
}
QPlainTextEdit {
    background: #0d131b;
    border: 1px solid #2a3543;
    border-radius: 5px;
    font-family: Consolas, monospace;
    font-size: 9pt;
}
QStatusBar {
    color: #8da1b4;
}
"""


class SliderField(QWidget):
    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        minimum: float,
        maximum: float,
        value: float = 0.0,
        decimals: int = 3,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.scale = 10000

        self.label = QLabel(label)
        self.label.setMinimumWidth(90)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self.scale)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(10 ** (-decimals))
        self.spin.setSuffix(suffix)
        self.spin.setMinimumWidth(110)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)

        self._sync_slider(value)
        self.spin.setValue(value)
        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)

    def _on_slider(self, position: int) -> None:
        span = self.maximum - self.minimum
        value = self.minimum + span * position / self.scale
        with QSignalBlocker(self.spin):
            self.spin.setValue(value)
        self.valueChanged.emit(self.spin.value())

    def _on_spin(self, value: float) -> None:
        self._sync_slider(value)
        self.valueChanged.emit(value)

    def _sync_slider(self, value: float) -> None:
        span = self.maximum - self.minimum
        position = 0 if span == 0 else int((value - self.minimum) / span * self.scale)
        with QSignalBlocker(self.slider):
            self.slider.setValue(max(0, min(self.scale, position)))

    def value(self) -> float:
        return self.spin.value()

    def set_value(self, value: float) -> None:
        self.spin.setValue(value)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DM Motor Tuner - DM-MC02 Bridge")
        self.resize(1440, 900)
        self.setMinimumSize(1180, 760)
        self.setStyleSheet(STYLESHEET)

        self.motors = self._load_config()
        self.feedback: dict[int, dm_motor.MotorFeedback] = {
            motor["number"]: dm_motor.MotorFeedback() for motor in self.motors
        }
        self.transport: Transport | None = None
        self.connected = False
        self.sequence = 0
        self._building_config_table = False

        self._build_ui()
        self._refresh_ports()
        self._select_motor(0)
        self._update_feedback_table()
        self._set_connected(False, "未连接")
        self.append_log("DM Motor Tuner 已启动。默认使用模拟器。")

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 13, 16, 10)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("DM MOTOR TUNER")
        title.setObjectName("Title")
        subtitle = QLabel("DM-MC02 bridge · six-motor configuration · live telemetry")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.conn_status = QLabel("● 未连接")
        self.conn_status.setObjectName("StatusOff")
        header.addWidget(self.conn_status)
        outer.addLayout(header)

        outer.addWidget(self._build_connection_group())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_motor_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_feedback_panel())
        splitter.setSizes([330, 700, 480])
        outer.addWidget(splitter, 1)

        self.statusBar().showMessage("就绪")

    def _build_connection_group(self) -> QGroupBox:
        group = QGroupBox("连接")
        layout = QHBoxLayout(group)

        layout.addWidget(QLabel("链路"))
        self.transport_combo = QComboBox()
        self.transport_combo.addItem("模拟器", "simulator")
        self.transport_combo.addItem("串口 / USB CDC", "serial")
        self.transport_combo.currentIndexChanged.connect(self._on_transport_type_changed)
        layout.addWidget(self.transport_combo)

        self.port_label = QLabel("串口")
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(230)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self._refresh_ports)
        layout.addWidget(self.port_label)
        layout.addWidget(self.port_combo)
        layout.addWidget(self.refresh_button)

        layout.addWidget(QLabel("波特率"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["921600", "115200", "1000000", "2000000"])
        layout.addWidget(self.baud_combo)
        layout.addStretch(1)

        self.connect_button = QPushButton("连接")
        self.connect_button.setObjectName("Connect")
        self.connect_button.clicked.connect(self._toggle_connection)
        layout.addWidget(self.connect_button)
        self._on_transport_type_changed()
        return group

    def _build_motor_panel(self) -> QGroupBox:
        group = QGroupBox("电机选择")
        group.setMinimumWidth(300)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        self.motor_combo = QComboBox()
        for motor in self.motors:
            self.motor_combo.addItem(
                f"{motor['number']} 号 - {motor['role']}", motor["number"]
            )
        self.motor_combo.currentIndexChanged.connect(self._select_motor)
        layout.addWidget(self.motor_combo)

        self.role_label = QLabel("—")
        self.role_label.setObjectName("RoleLabel")
        layout.addWidget(self.role_label)

        form = QFormLayout()
        self.bus_combo = QComboBox()
        self.bus_combo.addItem("CAN1", 0)
        self.bus_combo.addItem("CAN2", 1)
        self.id_spin = QSpinBox()
        self.id_spin.setRange(1, 127)
        self.id_spin.setDisplayIntegerBase(16)
        self.id_spin.setPrefix("0x")
        self.mst_spin = QSpinBox()
        self.mst_spin.setRange(0, 0x7FF)
        self.mst_spin.setDisplayIntegerBase(16)
        self.mst_spin.setPrefix("0x")
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("正向 +1", 1.0)
        self.direction_combo.addItem("反向 -1", -1.0)
        self.limit_spin = QDoubleSpinBox()
        self.limit_spin.setRange(0.05, 10.0)
        self.limit_spin.setDecimals(2)
        self.limit_spin.setSuffix(" N·m")
        form.addRow("总线", self.bus_combo)
        form.addRow("控制 ID", self.id_spin)
        form.addRow("反馈 ID", self.mst_spin)
        form.addRow("方向", self.direction_combo)
        form.addRow("扭矩限幅", self.limit_spin)
        layout.addLayout(form)

        for widget in (self.bus_combo, self.id_spin, self.mst_spin, self.direction_combo, self.limit_spin):
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._on_motor_config_changed)
            elif isinstance(widget, QDoubleSpinBox):
                widget.valueChanged.connect(self._on_motor_config_changed)
            else:
                widget.valueChanged.connect(self._on_motor_config_changed)

        buttons = QGridLayout()
        self.enable_button = QPushButton("使能")
        self.enable_button.setObjectName("Primary")
        self.disable_button = QPushButton("失能")
        self.disable_button.setObjectName("Danger")
        self.zero_button = QPushButton("设置零点")
        self.enable_button.clicked.connect(self._enable_selected)
        self.disable_button.clicked.connect(self._disable_selected)
        self.zero_button.clicked.connect(self._zero_selected)
        buttons.addWidget(self.enable_button, 0, 0)
        buttons.addWidget(self.disable_button, 0, 1)
        buttons.addWidget(self.zero_button, 1, 0, 1, 2)
        layout.addLayout(buttons)

        layout.addSpacing(6)
        all_row = QHBoxLayout()
        self.enable_all_button = QPushButton("全部使能")
        self.disable_all_button = QPushButton("全部失能")
        self.enable_all_button.clicked.connect(self._enable_all)
        self.disable_all_button.clicked.connect(self._disable_all)
        all_row.addWidget(self.enable_all_button)
        all_row.addWidget(self.disable_all_button)
        layout.addLayout(all_row)

        tip = QLabel(
            "说明：使能/失能使用当前 MCU 的 MIT 模式。\n"
            "真正写电机 ID/MST ID 前，需要下一步的桥接固件支持。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #7f93a7; font-size: 9pt;")
        layout.addWidget(tip)
        layout.addStretch(1)
        return group

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_mit_tab(), "MIT")
        self.tabs.addTab(self._build_position_velocity_tab(), "位置速度")
        self.tabs.addTab(self._build_speed_tab(), "速度")
        self.tabs.addTab(self._build_mcu_tab(), "MCU 参数")
        self.tabs.addTab(self._build_log_tab(), "通信日志")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

        bottom = QGroupBox("发送控制")
        bottom_layout = QHBoxLayout(bottom)
        self.periodic_check = QCheckBox("周期发送")
        self.periodic_check.toggled.connect(self._on_periodic_toggled)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 1000)
        self.interval_spin.setValue(20)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        self.periodic_label = QLabel("未启动")
        self.send_now_button = QPushButton("立即发送")
        self.send_now_button.setObjectName("Primary")
        self.send_now_button.clicked.connect(self._send_current)
        bottom_layout.addWidget(self.periodic_check)
        bottom_layout.addWidget(self.interval_spin)
        bottom_layout.addWidget(self.periodic_label)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.send_now_button)
        layout.addWidget(bottom)

        self.send_timer = QTimer(self)
        self.send_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.send_timer.timeout.connect(self._send_current)
        return panel

    def _build_mit_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)

        intro = QLabel("MIT 阻抗控制：τ = Kp × 位置误差 + Kd × 速度误差 + 前馈转矩")
        intro.setStyleSheet("color: #8fa8bd;")
        layout.addWidget(intro)

        self.mit_position = SliderField("目标位置", -12.5, 12.5, 0.0, 3, " rad")
        self.mit_velocity = SliderField("目标速度", -30.0, 30.0, 0.0, 2, " rad/s")
        self.mit_kp = SliderField("Kp", 0.0, 500.0, 0.0, 1)
        self.mit_kd = SliderField("Kd", 0.0, 5.0, 0.0, 3)
        self.mit_torque = SliderField("前馈扭矩", -10.0, 10.0, 0.0, 3, " N·m")
        for field in (
            self.mit_position,
            self.mit_velocity,
            self.mit_kp,
            self.mit_kd,
            self.mit_torque,
        ):
            layout.addWidget(field)

        layout.addStretch(1)
        return tab

    def _build_position_velocity_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        note = QLabel("位置速度模式：直接发送目标位置和速度（当前桥接固件尚未接入）。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #8fa8bd;")
        layout.addWidget(note)
        self.pv_position = SliderField("目标位置", -12.5, 12.5, 0.0, 3, " rad")
        self.pv_velocity = SliderField("目标速度", -30.0, 30.0, 0.0, 2, " rad/s")
        layout.addWidget(self.pv_position)
        layout.addWidget(self.pv_velocity)
        layout.addStretch(1)
        return tab

    def _build_speed_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        note = QLabel("速度模式：发送目标速度，单位 rad/s（当前桥接固件尚未接入）。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #8fa8bd;")
        layout.addWidget(note)
        self.speed_velocity = SliderField("目标速度", -30.0, 30.0, 0.0, 2, " rad/s")
        layout.addWidget(self.speed_velocity)
        layout.addStretch(1)
        return tab

    def _build_mcu_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        note = QLabel(
            "MCU 参数是正式轮腿固件使用的角色、方向、ID 和扭矩限幅。\n"
            "第一版先支持本地保存和下发；桥接固件完成后由 MCU 写入 Flash。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8fa8bd;")
        layout.addWidget(note)

        self.config_table = QTableWidget(6, 7)
        self.config_table.setHorizontalHeaderLabels(
            ["编号", "角色", "总线", "控制 ID", "反馈 ID", "方向", "扭矩限幅"]
        )
        self.config_table.verticalHeader().setVisible(False)
        self.config_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.config_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.config_table.cellChanged.connect(self._on_mcu_cell_changed)
        layout.addWidget(self.config_table, 1)

        row = QHBoxLayout()
        self.config_status = QLabel("尚未下发")
        self.config_status.setStyleSheet("color: #7f93a7;")
        self.save_config_button = QPushButton("保存本地")
        self.push_config_button = QPushButton("下发到 MCU")
        self.push_config_button.setObjectName("Primary")
        self.save_config_button.clicked.connect(self._save_local_config)
        self.push_config_button.clicked.connect(self._push_mcu_config)
        row.addWidget(self.config_status)
        row.addStretch(1)
        row.addWidget(self.save_config_button)
        row.addWidget(self.push_config_button)
        layout.addLayout(row)
        self._populate_config_table()
        return tab

    def _build_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2500)
        layout.addWidget(self.log_view, 1)

        raw = QGroupBox("原始 CAN 帧")
        raw_layout = QHBoxLayout(raw)
        self.raw_bus = QComboBox()
        self.raw_bus.addItem("CAN1", 0)
        self.raw_bus.addItem("CAN2", 1)
        self.raw_id = QLineEdit("03")
        self.raw_id.setPlaceholderText("CAN ID，十六进制")
        self.raw_id.setMaximumWidth(110)
        self.raw_data = QLineEdit()
        self.raw_data.setPlaceholderText("8 字节，例如 FF FF FF FF FF FF FF FC")
        self.raw_send_button = QPushButton("发送原始帧")
        self.raw_send_button.clicked.connect(self._send_raw_can)
        raw_layout.addWidget(self.raw_bus)
        raw_layout.addWidget(QLabel("ID"))
        raw_layout.addWidget(self.raw_id)
        raw_layout.addWidget(QLabel("数据"))
        raw_layout.addWidget(self.raw_data, 1)
        raw_layout.addWidget(self.raw_send_button)
        layout.addWidget(raw)

        row = QHBoxLayout()
        clear = QPushButton("清空日志")
        clear.clicked.connect(self.log_view.clear)
        row.addStretch(1)
        row.addWidget(clear)
        layout.addLayout(row)
        return tab

    def _build_feedback_panel(self) -> QGroupBox:
        group = QGroupBox("六电机实时反馈")
        group.setMinimumWidth(430)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)

        self.feedback_table = QTableWidget(6, 9)
        self.feedback_table.setHorizontalHeaderLabels(
            ["编号", "角色", "状态", "位置", "速度", "转矩", "MOS", "线圈", "故障"]
        )
        self.feedback_table.verticalHeader().setVisible(False)
        self.feedback_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.feedback_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.feedback_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.feedback_table.setAlternatingRowColors(True)
        self.feedback_table.setWordWrap(False)
        for row, motor in enumerate(self.motors):
            self.feedback_table.setItem(row, 0, QTableWidgetItem(str(motor["number"])))
            self.feedback_table.setItem(row, 1, QTableWidgetItem(motor["role"]))
            for column in range(2, 9):
                self.feedback_table.setItem(row, column, QTableWidgetItem("—"))
        layout.addWidget(self.feedback_table, 1)

        legend = QLabel(
            "绿色：使能正常  ·  灰色：失能  ·  红色：故障\n"
            "反馈 ID：1～6 号依次为 0x11～0x16"
        )
        legend.setStyleSheet("color: #72879b; font-size: 9pt;")
        layout.addWidget(legend)
        return group

    # --------------------------------------------------------------- config
    def _load_config(self) -> list[dict[str, Any]]:
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                motors = data.get("motors", [])
                if isinstance(motors, list) and len(motors) == 6:
                    return motors
            except (OSError, json.JSONDecodeError):
                pass
        return [dict(motor) for motor in MOTOR_DEFAULTS]

    def _save_config(self, notify: bool = True) -> None:
        CONFIG_PATH.write_text(
            json.dumps({"motors": self.motors}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if notify:
            self.config_status.setText(f"本地配置已保存: {CONFIG_PATH.name}")

    def _populate_config_table(self) -> None:
        self._building_config_table = True
        with QSignalBlocker(self.config_table):
            for row, motor in enumerate(self.motors):
                values = [
                    str(motor["number"]),
                    str(motor["role"]),
                    "CAN1" if int(motor["bus"]) == 0 else "CAN2",
                    f"0x{int(motor['control_id']):02X}",
                    f"0x{int(motor['mst_id']):02X}",
                    "正向 +1" if float(motor["direction"]) >= 0 else "反向 -1",
                    f"{float(motor['torque_limit']):.1f}",
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.config_table.setItem(row, column, item)
        self._building_config_table = False

    def _on_mcu_cell_changed(self, row: int, column: int) -> None:
        if self._building_config_table:
            return
        try:
            motor = self.motors[row]
            text = self.config_table.item(row, column).text().strip()
            if column == 1:
                motor["role"] = text
            elif column == 2:
                motor["bus"] = 0 if text.upper() == "CAN1" else 1
            elif column == 3:
                motor["control_id"] = int(text, 0)
            elif column == 4:
                motor["mst_id"] = int(text, 0)
            elif column == 5:
                motor["direction"] = 1.0 if "正向" in text or "+1" in text else -1.0
            elif column == 6:
                motor["torque_limit"] = float(text)
        except (ValueError, IndexError, AttributeError):
            self.config_status.setText("参数格式错误，请检查该项")
            return
        self._sync_motor_labels(row)
        self._save_config(notify=False)
        self.config_status.setText("参数已修改，尚未下发")

    def _sync_motor_labels(self, row: int) -> None:
        motor = self.motors[row]
        if row == self.motor_combo.currentIndex():
            self.role_label.setText(str(motor["role"]))
        self.feedback_table.item(row, 1).setText(str(motor["role"]))
        self.motor_combo.setItemText(
            row, f"{motor['number']} 号 - {motor['role']}"
        )

    def _on_motor_config_changed(self) -> None:
        index = self.motor_combo.currentIndex()
        if index < 0 or index >= len(self.motors):
            return
        motor = self.motors[index]
        motor["bus"] = int(self.bus_combo.currentData())
        motor["control_id"] = self.id_spin.value()
        motor["mst_id"] = self.mst_spin.value()
        motor["direction"] = float(self.direction_combo.currentData())
        motor["torque_limit"] = self.limit_spin.value()
        self._populate_config_table()
        self._save_config(notify=False)

    def _select_motor(self, index: int) -> None:
        if index < 0 or index >= len(self.motors):
            return
        motor = self.motors[index]
        with QSignalBlocker(self.bus_combo), QSignalBlocker(self.id_spin), QSignalBlocker(self.mst_spin), QSignalBlocker(self.direction_combo), QSignalBlocker(self.limit_spin):
            self.role_label.setText(str(motor["role"]))
            self.bus_combo.setCurrentIndex(int(motor["bus"]))
            self.id_spin.setValue(int(motor["control_id"]))
            self.mst_spin.setValue(int(motor["mst_id"]))
            self.direction_combo.setCurrentIndex(0 if float(motor["direction"]) >= 0 else 1)
            self.limit_spin.setValue(float(motor["torque_limit"]))

    # ------------------------------------------------------------- connect
    def _refresh_ports(self) -> None:
        current = self.port_combo.currentData()
        self.port_combo.clear()
        ports = available_serial_ports()
        for port_name, label in ports:
            self.port_combo.addItem(label, port_name)
        if current:
            index = self.port_combo.findData(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        if not ports:
            self.port_combo.addItem("未发现串口", "")
        self.append_log(f"发现 {len(ports)} 个串口")

    def _on_transport_type_changed(self) -> None:
        is_serial = self.transport_combo.currentData() == "serial"
        self.port_label.setVisible(is_serial)
        self.port_combo.setVisible(is_serial)
        self.refresh_button.setVisible(is_serial)
        self.baud_combo.setVisible(is_serial)

    def _toggle_connection(self) -> None:
        if self.transport is not None:
            was_connected = self.connected
            self._disconnect()
            if was_connected:
                return

        if self.transport_combo.currentData() == "serial":
            port = self.port_combo.currentData()
            baud = int(self.baud_combo.currentText())
            transport: Transport = SerialTransport(str(port or ""), baud, self)
        else:
            transport = SimulatorTransport(self)

        transport.connection_changed.connect(self._on_connection_changed)
        transport.frame_received.connect(self._on_frame_received)
        transport.error.connect(self._on_transport_error)
        transport.log.connect(self.append_log)
        self.transport = transport
        transport.open()

    def _disconnect(self) -> None:
        self.send_timer.stop()
        self.periodic_check.setChecked(False)
        if self.transport is not None:
            self.transport.close()
            self.transport.deleteLater()
            self.transport = None
        self._set_connected(False, "未连接")
        self.connect_button.setText("连接")

    def _on_connection_changed(self, connected: bool, message: str) -> None:
        self._set_connected(connected, message)
        if connected and isinstance(self.transport, SerialTransport):
            self._send_protocol(ping_frame(self._next_sequence()))
            self._send_protocol(stream_start_frame(True, self._next_sequence()))

    def _set_connected(self, connected: bool, message: str) -> None:
        self.connected = bool(connected)
        if connected:
            self.conn_status.setText(f"● 已连接 · {message}")
            self.conn_status.setObjectName("StatusOk")
            self.connect_button.setText("断开")
            self.statusBar().showMessage(message)
        else:
            self.conn_status.setText(f"● {message}")
            self.conn_status.setObjectName("StatusOff")
            self.connect_button.setText("连接")
            self.statusBar().showMessage(message)
        self.conn_status.style().unpolish(self.conn_status)
        self.conn_status.style().polish(self.conn_status)
        self.enable_button.setEnabled(connected)
        self.disable_button.setEnabled(connected)
        self.zero_button.setEnabled(connected)
        self.enable_all_button.setEnabled(connected)
        self.disable_all_button.setEnabled(connected)
        self.send_now_button.setEnabled(connected)
        self.periodic_check.setEnabled(connected)

    def _on_transport_error(self, message: str) -> None:
        self.append_log(f"错误: {message}")
        self.statusBar().showMessage(message)

    # -------------------------------------------------------------- sending
    def _next_sequence(self) -> int:
        self.sequence = (self.sequence + 1) & 0xFFFF
        return self.sequence

    def _send_protocol(self, frame: Frame) -> bool:
        if self.transport is None:
            self.append_log("未连接，无法发送")
            return False
        self.transport.send_frame(frame)
        return True

    def _send_can(self, can: CanFrame) -> bool:
        return self._send_protocol(can_tx_frame(can, self._next_sequence()))

    def _selected_motor(self) -> dict[str, Any]:
        index = max(0, self.motor_combo.currentIndex())
        return self.motors[index]

    def _motor_can(self) -> CanFrame:
        motor = self._selected_motor()
        return dm_motor.mit_frame(
            int(motor["bus"]),
            int(motor["control_id"]),
            self.mit_position.value() * float(motor["direction"]),
            self.mit_velocity.value() * float(motor["direction"]),
            self.mit_kp.value(),
            self.mit_kd.value(),
            self.mit_torque.value() * float(motor["direction"]),
        )

    def _enable_selected(self) -> None:
        motor = self._selected_motor()
        self._send_can(
            dm_motor.enable_frame(int(motor["bus"]), int(motor["control_id"]))
        )

    def _disable_selected(self) -> None:
        motor = self._selected_motor()
        self._send_can(
            dm_motor.disable_frame(int(motor["bus"]), int(motor["control_id"]))
        )

    def _zero_selected(self) -> None:
        motor = self._selected_motor()
        answer = QMessageBox.question(
            self,
            "设置零点",
            f"确定将 {motor['number']} 号电机当前位置设为零点吗？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._send_can(
            dm_motor.set_zero_frame(int(motor["bus"]), int(motor["control_id"]))
        )

    def _enable_all(self) -> None:
        for motor in self.motors:
            self._send_can(
                dm_motor.enable_frame(int(motor["bus"]), int(motor["control_id"]))
            )

    def _disable_all(self) -> None:
        for motor in self.motors:
            self._send_can(
                dm_motor.disable_frame(int(motor["bus"]), int(motor["control_id"]))
            )

    def _on_periodic_toggled(self, checked: bool) -> None:
        if checked:
            if self.transport is None:
                self.periodic_check.setChecked(False)
                return
            self.send_timer.start(self.interval_spin.value())
            self.periodic_label.setText(f"运行中 · {self.interval_spin.value()} ms")
        else:
            self.send_timer.stop()
            self.periodic_label.setText("未启动")

    def _on_interval_changed(self, value: int) -> None:
        if self.send_timer.isActive():
            self.send_timer.start(value)
            self.periodic_label.setText(f"运行中 · {value} ms")

    def _on_tab_changed(self, index: int) -> None:
        supported = index in (0, 1, 2)
        self.periodic_check.setEnabled(self.transport is not None and supported)
        self.send_now_button.setEnabled(self.transport is not None and supported)
        if not supported:
            self.periodic_check.setChecked(False)

    def _send_current(self) -> None:
        if self.transport is None:
            return
        tab = self.tabs.currentIndex()
        motor = self._selected_motor()
        if tab == 0:
            self.send_now_button.setEnabled(False)
            try:
                self._send_can(self._motor_can())
            finally:
                self.send_now_button.setEnabled(True)
        elif tab == 1:
            self._send_can(
                dm_motor.position_velocity_frame(
                    int(motor["bus"]),
                    int(motor["control_id"]),
                    self.pv_position.value() * float(motor["direction"]),
                    self.pv_velocity.value() * float(motor["direction"]),
                )
            )
        elif tab == 2:
            self._send_can(
                dm_motor.speed_frame(
                    int(motor["bus"]),
                    int(motor["control_id"]),
                    self.speed_velocity.value() * float(motor["direction"]),
                )
            )

    def _send_raw_can(self) -> None:
        try:
            can_id = int(self.raw_id.text().strip(), 16)
            data = bytes.fromhex(self.raw_data.text().replace(",", " ").strip())
            if len(data) > 8:
                raise ValueError("数据不能超过 8 字节")
        except ValueError as exc:
            QMessageBox.warning(self, "CAN 数据错误", str(exc))
            return
        self._send_can(CanFrame(int(self.raw_bus.currentData()), can_id, data))

    # --------------------------------------------------------------- feedback
    def _on_frame_received(self, frame: Frame) -> None:
        if frame.command == Command.CAN_RX:
            try:
                can = CanFrame.unpack(frame.payload)
                self._handle_can_feedback(can)
            except ValueError as exc:
                self.append_log(f"无效 CAN_RX: {exc}")
        elif frame.command == Command.ACK:
            self.append_log(f"MCU ACK: {frame.payload.decode('utf-8', errors='replace')}")
        elif frame.command == Command.NACK:
            self.append_log(f"MCU NACK: {frame.payload.hex(' ')}")
        elif frame.command == Command.LOG:
            self.append_log(f"MCU: {frame.payload.decode('utf-8', errors='replace')}")

    def _handle_can_feedback(self, can: CanFrame) -> None:
        by_master = {
            (int(motor["bus"]), int(motor["mst_id"])): int(motor["number"])
            for motor in self.motors
        }
        number = by_master.get((can.bus, can.can_id))
        if number is None:
            return
        try:
            feedback = dm_motor.decode_feedback(can.data)
        except ValueError:
            return
        self.feedback[number] = feedback
        self._update_feedback_row(number)

    def _feedback_row_for_number(self, number: int) -> int:
        for index, motor in enumerate(self.motors):
            if int(motor["number"]) == number:
                return index
        return max(0, min(5, number - 1))

    def _update_feedback_table(self) -> None:
        for motor in self.motors:
            self._update_feedback_row(int(motor["number"]))

    def _update_feedback_row(self, number: int) -> None:
        row = self._feedback_row_for_number(number)
        feedback = self.feedback.get(number, dm_motor.MotorFeedback())
        motor = self.motors[row]
        color = QColor("#6f8294")
        if feedback.state == 1:
            color = QColor("#61d7b3")
        elif feedback.state != 0:
            color = QColor("#ff7b86")

        fault_text = "—" if feedback.state == 0 else ("正常" if feedback.state == 1 else feedback.state_text)
        values = [
            str(motor["number"]),
            str(motor["role"]),
            "使能" if feedback.state == 1 else feedback.state_text,
            f"{feedback.position:+.3f}",
            f"{feedback.velocity:+.2f}",
            f"{feedback.torque:+.2f}",
            f"{feedback.mos_temperature:.0f}°C",
            f"{feedback.coil_temperature:.0f}°C",
            fault_text,
        ]
        for column, value in enumerate(values):
            item = self.feedback_table.item(row, column)
            if item is None:
                item = QTableWidgetItem()
                self.feedback_table.setItem(row, column, item)
            item.setText(value)
            if column in (2, 8):
                item.setForeground(color)

    # ------------------------------------------------------------------ MCU
    def _save_local_config(self) -> None:
        self._save_config(notify=True)
        self.append_log(f"MCU 配置已保存到 {CONFIG_PATH}")

    def _push_mcu_config(self) -> None:
        payload = json.dumps({"motors": self.motors}, ensure_ascii=False).encode("utf-8")
        if len(payload) > 512:
            QMessageBox.warning(self, "配置过大", "MCU 配置超过协议单帧 512 字节")
            return
        if self._send_protocol(Frame(Command.MCU_CONFIG_SET, payload, self._next_sequence())):
            self.config_status.setText("已下发，等待 MCU 确认")
            self.append_log("已下发 MCU 六电机配置")

    # ------------------------------------------------------------------ misc
    def append_log(self, message: str) -> None:
        timestamp = QTime.currentTime().toString("HH:mm:ss.zzz")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.send_timer.stop()
        if self.transport is not None:
            self.transport.close()
        super().closeEvent(event)
