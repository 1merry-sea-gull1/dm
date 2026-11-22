"""DM4310 protocol helpers used by the desktop application."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .protocol import CanFrame


@dataclass(frozen=True)
class MotorLimits:
    p_min: float = -12.5
    p_max: float = 12.5
    v_min: float = -30.0
    v_max: float = 30.0
    t_min: float = -10.0
    t_max: float = 10.0
    kp_min: float = 0.0
    kp_max: float = 500.0
    kd_min: float = 0.0
    kd_max: float = 5.0


DEFAULT_LIMITS = MotorLimits()

MODE_MIT = 0x000
MODE_POS_VEL = 0x100
MODE_SPEED = 0x200
MODE_POS_FORCE = 0x300

MODE_LABELS = {
    MODE_MIT: "MIT",
    MODE_POS_VEL: "位置速度",
    MODE_SPEED: "速度",
    MODE_POS_FORCE: "力位混控",
}

ERROR_LABELS = {
    0: "失能",
    1: "使能",
    8: "过压",
    9: "欠压",
    10: "过流",
    11: "MOS过温",
    12: "线圈过温",
    13: "通讯丢失",
    14: "过载",
}

PARAM_MST_ID = 7
PARAM_ESC_ID = 8
PARAM_TIMEOUT = 9
PARAM_CTRL_MODE = 10


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def float_to_uint(value: float, minimum: float, maximum: float, bits: int) -> int:
    value = clamp(value, minimum, maximum)
    span = maximum - minimum
    if span == 0:
        return 0
    return int((value - minimum) * ((1 << bits) - 1) / span)


def uint_to_float(value: int, minimum: float, maximum: float, bits: int) -> float:
    span = maximum - minimum
    return value * span / ((1 << bits) - 1) + minimum


def mit_frame(
    bus: int,
    motor_id: int,
    position: float,
    velocity: float,
    kp: float,
    kd: float,
    torque: float,
    limits: MotorLimits = DEFAULT_LIMITS,
) -> CanFrame:
    pos_tmp = float_to_uint(position, limits.p_min, limits.p_max, 16)
    vel_tmp = float_to_uint(velocity, limits.v_min, limits.v_max, 12)
    kp_tmp = float_to_uint(kp, limits.kp_min, limits.kp_max, 12)
    kd_tmp = float_to_uint(kd, limits.kd_min, limits.kd_max, 12)
    tor_tmp = float_to_uint(torque, limits.t_min, limits.t_max, 12)

    data = bytes(
        (
            (pos_tmp >> 8) & 0xFF,
            pos_tmp & 0xFF,
            (vel_tmp >> 4) & 0xFF,
            ((vel_tmp & 0x0F) << 4) | ((kp_tmp >> 8) & 0x0F),
            kp_tmp & 0xFF,
            (kd_tmp >> 4) & 0xFF,
            ((kd_tmp & 0x0F) << 4) | ((tor_tmp >> 8) & 0x0F),
            tor_tmp & 0xFF,
        )
    )
    return CanFrame(bus=bus, can_id=motor_id + MODE_MIT, data=data)


def position_velocity_frame(bus: int, motor_id: int, position: float, velocity: float) -> CanFrame:
    return CanFrame(
        bus=bus,
        can_id=motor_id + MODE_POS_VEL,
        data=struct.pack("<ff", position, velocity),
    )


def speed_frame(bus: int, motor_id: int, velocity: float) -> CanFrame:
    return CanFrame(bus=bus, can_id=motor_id + MODE_SPEED, data=struct.pack("<f", velocity))


def control_command_frame(bus: int, motor_id: int, mode: int, command: int) -> CanFrame:
    if command not in (0xFC, 0xFD, 0xFE, 0xFB):
        raise ValueError("unsupported DM control command")
    return CanFrame(bus=bus, can_id=motor_id + mode, data=b"\xFF" * 7 + bytes((command,)))


def enable_frame(bus: int, motor_id: int, mode: int = MODE_MIT) -> CanFrame:
    return control_command_frame(bus, motor_id, mode, 0xFC)


def disable_frame(bus: int, motor_id: int, mode: int = MODE_MIT) -> CanFrame:
    return control_command_frame(bus, motor_id, mode, 0xFD)


def set_zero_frame(bus: int, motor_id: int, mode: int = MODE_MIT) -> CanFrame:
    return control_command_frame(bus, motor_id, mode, 0xFE)


def parameter_read_frame(bus: int, motor_id: int, register: int) -> CanFrame:
    payload = bytes((motor_id & 0xFF, (motor_id >> 8) & 0xFF, 0x33, register & 0xFF, 0, 0, 0, 0))
    return CanFrame(bus=bus, can_id=0x7FF, data=payload)


def parameter_write_frame(bus: int, motor_id: int, register: int, value: int | float) -> CanFrame:
    if register in (PARAM_MST_ID, PARAM_ESC_ID, PARAM_TIMEOUT, PARAM_CTRL_MODE):
        value_bytes = struct.pack("<I", int(value) & 0xFFFFFFFF)
    else:
        value_bytes = struct.pack("<f", float(value))
    payload = (
        bytes((motor_id & 0xFF, (motor_id >> 8) & 0xFF, 0x55, register & 0xFF))
        + value_bytes
    )
    return CanFrame(bus=bus, can_id=0x7FF, data=payload)


def save_parameters_frame(bus: int, motor_id: int) -> CanFrame:
    payload = bytes((motor_id & 0xFF, (motor_id >> 8) & 0xFF, 0xAA, 0x01, 0, 0, 0, 0))
    return CanFrame(bus=bus, can_id=0x7FF, data=payload)


@dataclass(frozen=True)
class MotorFeedback:
    motor_id: int = 0
    state: int = 0
    position: float = 0.0
    velocity: float = 0.0
    torque: float = 0.0
    mos_temperature: float = 0.0
    coil_temperature: float = 0.0

    @property
    def state_text(self) -> str:
        return ERROR_LABELS.get(self.state, f"错误 {self.state}")


def decode_feedback(data: bytes, limits: MotorLimits = DEFAULT_LIMITS) -> MotorFeedback:
    if len(data) < 8:
        raise ValueError("DM feedback frame must be 8 bytes")
    motor_id = data[0] & 0x0F
    state = (data[0] >> 4) & 0x0F
    p_int = (data[1] << 8) | data[2]
    v_int = (data[3] << 4) | (data[4] >> 4)
    t_int = ((data[4] & 0x0F) << 8) | data[5]
    return MotorFeedback(
        motor_id=motor_id,
        state=state,
        position=uint_to_float(p_int, limits.p_min, limits.p_max, 16),
        velocity=uint_to_float(v_int, limits.v_min, limits.v_max, 12),
        torque=uint_to_float(t_int, limits.t_min, limits.t_max, 12),
        mos_temperature=float(data[6]),
        coil_temperature=float(data[7]),
    )


def encode_feedback(
    motor_id: int,
    state: int,
    position: float,
    velocity: float,
    torque: float,
    mos_temperature: float,
    coil_temperature: float,
    limits: MotorLimits = DEFAULT_LIMITS,
) -> bytes:
    p_int = float_to_uint(position, limits.p_min, limits.p_max, 16)
    v_int = float_to_uint(velocity, limits.v_min, limits.v_max, 12)
    t_int = float_to_uint(torque, limits.t_min, limits.t_max, 12)
    mos = int(clamp(mos_temperature, 0, 255))
    coil = int(clamp(coil_temperature, 0, 255))
    return bytes(
        (
            ((state & 0x0F) << 4) | (motor_id & 0x0F),
            (p_int >> 8) & 0xFF,
            p_int & 0xFF,
            (v_int >> 4) & 0xFF,
            ((v_int & 0x0F) << 4) | ((t_int >> 8) & 0x0F),
            t_int & 0xFF,
            mos,
            coil,
        )
    )
