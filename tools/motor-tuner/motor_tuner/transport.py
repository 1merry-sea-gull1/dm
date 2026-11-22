"""Transport backends: real USB CDC serial port and an in-process simulator."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from PySide6.QtCore import QIODevice, QObject, QTimer, Qt, Signal
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

from . import dm_motor
from .protocol import (
    CanFrame,
    Command,
    Frame,
    FrameParser,
    can_rx_frame,
    encode_frame,
)


class Transport(QObject):
    frame_received = Signal(object)
    connection_changed = Signal(bool, str)
    error = Signal(str)
    log = Signal(str)

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def send_frame(self, frame: Frame) -> None:
        raise NotImplementedError


def available_serial_ports() -> list[tuple[str, str]]:
    ports = []
    for info in QSerialPortInfo.availablePorts():
        label = f"{info.portName()} - {info.description()}" if info.description() else info.portName()
        ports.append((info.portName(), label))
    return ports


class SerialTransport(Transport):
    def __init__(self, port_name: str, baud: int = 921600, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.port_name = port_name
        self.baud = baud
        self._parser = FrameParser()
        self._serial = QSerialPort(self)
        self._serial.setPortName(port_name)
        self._serial.setBaudRate(baud)
        self._serial.setDataBits(QSerialPort.DataBits.Data8)
        self._serial.setParity(QSerialPort.Parity.NoParity)
        self._serial.setStopBits(QSerialPort.StopBits.OneStop)
        self._serial.setFlowControl(QSerialPort.FlowControl.NoFlowControl)
        self._serial.readyRead.connect(self._on_ready_read)
        self._serial.errorOccurred.connect(self._on_serial_error)

    def open(self) -> None:
        if not self.port_name:
            self.error.emit("未选择串口")
            self.connection_changed.emit(False, "未选择串口")
            return
        if not self._serial.open(QIODevice.OpenModeFlag.ReadWrite):
            message = f"无法打开 {self.port_name}: {self._serial.errorString()}"
            self.error.emit(message)
            self.connection_changed.emit(False, message)
            return
        self._serial.clear()
        self._parser.reset()
        self.connection_changed.emit(True, f"已连接 {self.port_name} @ {self.baud}")
        self.log.emit(f"串口已打开: {self.port_name}, {self.baud} 8N1")

    def close(self) -> None:
        if self._serial.isOpen():
            self._serial.close()
        self.connection_changed.emit(False, "串口已关闭")

    def send_frame(self, frame: Frame) -> None:
        if not self._serial.isOpen():
            self.error.emit("串口未连接")
            return
        raw = encode_frame(frame)
        written = self._serial.write(raw)
        if written < 0:
            self.error.emit(f"串口写入失败: {self._serial.errorString()}")
            return
        self.log.emit(f"TX {frame.command_name}  {raw.hex(' ').upper()}")

    def _on_ready_read(self) -> None:
        data = bytes(self._serial.readAll())
        if not data:
            return
        for frame in self._parser.feed(data):
            self.log.emit(f"RX {frame.command_name}  {frame.payload.hex(' ').upper()}")
            self.frame_received.emit(frame)

    def _on_serial_error(self, error: QSerialPort.SerialPortError) -> None:
        if error == QSerialPort.SerialPortError.NoError:
            return
        message = f"串口错误: {self._serial.errorString()}"
        self.error.emit(message)
        if error in (
            QSerialPort.SerialPortError.ResourceError,
            QSerialPort.SerialPortError.DeviceNotFoundError,
            QSerialPort.SerialPortError.PermissionError,
        ):
            self.connection_changed.emit(False, message)


@dataclass
class SimMotor:
    number: int
    role: str
    bus: int
    control_id: int
    mst_id: int
    position: float = 0.0
    velocity: float = 0.0
    torque: float = 0.0
    target_position: float = 0.0
    target_velocity: float = 0.0
    kp: float = 0.0
    kd: float = 0.0
    feedforward: float = 0.0
    enabled: bool = False
    mos_temperature: float = 28.0
    coil_temperature: float = 27.0


class SimulatorTransport(Transport):
    """Small behavioral model of the bridge and six motors.

    It intentionally implements only the parts needed by the first UI
    milestone: MIT control, enable/disable/zero, feedback and MCU config echo.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._connected = False
        self._streaming = True
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._tick)
        self._last_tick = time.monotonic()
        self._motors = [
            SimMotor(1, "右侧关节 0", 0, 0x01, 0x11, position=0.00),
            SimMotor(2, "右侧轮毂", 0, 0x02, 0x12, position=0.00),
            SimMotor(3, "右侧关节 1", 0, 0x03, 0x13, position=0.00),
            SimMotor(4, "左侧关节 0", 1, 0x04, 0x14, position=0.00),
            SimMotor(5, "左侧轮毂", 1, 0x05, 0x15, position=0.00),
            SimMotor(6, "左侧关节 1", 1, 0x06, 0x16, position=0.00),
        ]

    def open(self) -> None:
        self._connected = True
        self._last_tick = time.monotonic()
        self._timer.start()
        self.connection_changed.emit(True, "模拟器已连接")
        self.log.emit("模拟器启动：六个电机反馈以 50 Hz 运行")

    def close(self) -> None:
        self._timer.stop()
        self._connected = False
        self.connection_changed.emit(False, "模拟器已关闭")

    def send_frame(self, frame: Frame) -> None:
        self.log.emit(f"TX {frame.command_name}  {frame.payload.hex(' ').upper()}")

        if frame.command == Command.PING:
            self.frame_received.emit(Frame(Command.ACK, b"DM-MC02-SIM", frame.sequence))
            return
        if frame.command == Command.CAN_STREAM_START:
            self._streaming = True
            return
        if frame.command == Command.CAN_STREAM_STOP:
            self._streaming = False
            return
        if frame.command == Command.MCU_CONFIG_SET:
            self._apply_mcu_config(frame.payload)
            self.frame_received.emit(Frame(Command.ACK, b"CONFIG", frame.sequence))
            return
        if frame.command == Command.CAN_TX:
            try:
                self._handle_can(CanFrame.unpack(frame.payload))
            except (ValueError, IndexError) as exc:
                self.error.emit(f"模拟器收到无效 CAN 帧: {exc}")

    def _apply_mcu_config(self, payload: bytes) -> None:
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        motors = data.get("motors")
        if not isinstance(motors, list):
            return
        for item in motors:
            try:
                number = int(item["number"])
                motor = self._find_by_number(number)
                if motor is None:
                    continue
                motor.role = str(item.get("role", motor.role))
                motor.bus = int(item.get("bus", motor.bus))
                motor.control_id = int(item.get("control_id", motor.control_id))
                motor.mst_id = int(item.get("mst_id", motor.mst_id))
            except (KeyError, TypeError, ValueError):
                continue

    def _find_by_number(self, number: int) -> SimMotor | None:
        return next((motor for motor in self._motors if motor.number == number), None)

    def _handle_can(self, can: CanFrame) -> None:
        if can.can_id == 0x7FF:
            return
        mode = can.can_id & 0x300
        control_id = can.can_id & 0xFF
        motor = next(
            (
                item
                for item in self._motors
                if item.control_id == control_id and item.bus == can.bus
            ),
            None,
        )
        if motor is None:
            return

        data = can.data
        if len(data) == 8 and data[:7] == b"\xFF" * 7:
            command = data[7]
            if command == 0xFC:
                motor.enabled = True
                motor.target_position = motor.position
                self.log.emit(f"模拟器: {motor.number}号电机使能")
            elif command == 0xFD:
                motor.enabled = False
                motor.feedforward = 0.0
                motor.kp = 0.0
                motor.kd = 0.0
                self.log.emit(f"模拟器: {motor.number}号电机失能")
            elif command == 0xFE:
                motor.position = 0.0
                motor.velocity = 0.0
                motor.target_position = 0.0
                self.log.emit(f"模拟器: {motor.number}号电机置零")
            return

        if not motor.enabled:
            return

        if mode == dm_motor.MODE_MIT and len(data) == 8:
            p_int = (data[0] << 8) | data[1]
            v_int = (data[2] << 4) | (data[3] >> 4)
            kp_int = ((data[3] & 0x0F) << 8) | data[4]
            kd_int = (data[5] << 4) | (data[6] >> 4)
            t_int = ((data[6] & 0x0F) << 8) | data[7]
            limits = dm_motor.DEFAULT_LIMITS
            motor.target_position = dm_motor.uint_to_float(
                p_int, limits.p_min, limits.p_max, 16
            )
            motor.target_velocity = dm_motor.uint_to_float(
                v_int, limits.v_min, limits.v_max, 12
            )
            motor.kp = dm_motor.uint_to_float(kp_int, limits.kp_min, limits.kp_max, 12)
            motor.kd = dm_motor.uint_to_float(kd_int, limits.kd_min, limits.kd_max, 12)
            motor.feedforward = dm_motor.uint_to_float(
                t_int, limits.t_min, limits.t_max, 12
            )
        elif mode == dm_motor.MODE_POS_VEL and len(data) >= 8:
            import struct

            position, velocity = struct.unpack("<ff", data[:8])
            motor.target_position = position
            motor.target_velocity = velocity
            motor.kp = 10.0
            motor.kd = 1.0
            motor.feedforward = 0.0
        elif mode == dm_motor.MODE_SPEED and len(data) >= 4:
            import struct

            motor.target_velocity = struct.unpack("<f", data[:4])[0]
            motor.kp = 0.0
            motor.kd = 2.0
            motor.feedforward = 0.0

    def _tick(self) -> None:
        if not self._connected:
            return
        now = time.monotonic()
        dt = max(0.001, min(0.05, now - self._last_tick))
        self._last_tick = now

        for motor in self._motors:
            if motor.enabled:
                torque_cmd = (
                    motor.kp * (motor.target_position - motor.position)
                    + motor.kd * (motor.target_velocity - motor.velocity)
                    + motor.feedforward
                )
                motor.torque = max(-10.0, min(10.0, torque_cmd))
                acceleration = motor.torque * 1.8 - motor.velocity * 0.25
                motor.velocity += acceleration * dt
                motor.position += motor.velocity * dt
                motor.position = max(-12.4, min(12.4, motor.position))
                motor.mos_temperature += abs(motor.torque) * 0.05 * dt
                motor.coil_temperature += abs(motor.torque) * 0.04 * dt
            else:
                motor.torque = 0.0
                motor.velocity *= max(0.0, 1.0 - 3.0 * dt)
                motor.position += motor.velocity * dt

            motor.mos_temperature += (28.0 - motor.mos_temperature) * 0.005
            motor.coil_temperature += (27.0 - motor.coil_temperature) * 0.005

        if self._streaming:
            for motor in self._motors:
                data = dm_motor.encode_feedback(
                    motor.control_id,
                    1 if motor.enabled else 0,
                    motor.position,
                    motor.velocity,
                    motor.torque,
                    motor.mos_temperature,
                    motor.coil_temperature,
                )
                self.frame_received.emit(
                    can_rx_frame(CanFrame(motor.bus, motor.mst_id, data))
                )
