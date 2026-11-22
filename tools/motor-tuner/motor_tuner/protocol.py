"""PC <-> DM-MC02 bridge protocol.

Frame layout (little endian):

    magic(2) | version(1) | command(1) | sequence(2) | length(2) | payload | crc16(2)

The CRC is CRC-16/CCITT-FALSE over version..payload, i.e. all bytes after
the magic and before the CRC.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable

MAGIC = b"\xA5\x5A"
VERSION = 1
MAX_PAYLOAD = 512
HEADER = struct.Struct("<2sBBHH")
CRC = struct.Struct("<H")


class Command(IntEnum):
    PING = 0x01
    GET_INFO = 0x02
    ACK = 0x03
    NACK = 0x04

    CAN_TX = 0x10
    CAN_RX = 0x11
    CAN_STREAM_START = 0x12
    CAN_STREAM_STOP = 0x13

    MOTOR_PARAM_READ = 0x20
    MOTOR_PARAM_WRITE = 0x21

    MCU_CONFIG_GET = 0x30
    MCU_CONFIG_SET = 0x31
    MCU_CONFIG_SAVE = 0x32
    MCU_CONFIG_RESET = 0x33
    LOG = 0x40


COMMAND_NAMES = {int(command): command.name for command in Command}


def crc16_ccitt(data: bytes, initial: int = 0xFFFF) -> int:
    crc = initial
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class Frame:
    command: int
    payload: bytes = b""
    sequence: int = 0

    @property
    def command_name(self) -> str:
        return COMMAND_NAMES.get(int(self.command), f"0x{int(self.command):02X}")


def encode_frame(frame: Frame) -> bytes:
    payload = bytes(frame.payload)
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload too large: {len(payload)}")
    body = struct.pack(
        "<BBHH",
        VERSION,
        int(frame.command) & 0xFF,
        frame.sequence & 0xFFFF,
        len(payload),
    ) + payload
    return MAGIC + body + CRC.pack(crc16_ccitt(body))


class FrameParser:
    """Incremental frame decoder suitable for a byte stream (USB CDC/UART)."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[Frame]:
        self._buffer.extend(data)
        frames: list[Frame] = []

        while True:
            start = self._buffer.find(MAGIC)
            if start < 0:
                # Keep the last byte in case the magic is split across reads.
                if len(self._buffer) > 1:
                    del self._buffer[:-1]
                return frames
            if start:
                del self._buffer[:start]
            if len(self._buffer) < HEADER.size:
                return frames

            _, version, command, sequence, length = HEADER.unpack_from(self._buffer)
            if version != VERSION or length > MAX_PAYLOAD:
                del self._buffer[0]
                continue

            total = HEADER.size + length + CRC.size
            if len(self._buffer) < total:
                return frames

            payload = bytes(self._buffer[HEADER.size : HEADER.size + length])
            expected_crc = CRC.unpack_from(self._buffer, HEADER.size + length)[0]
            body = bytes(self._buffer[2 : HEADER.size + length])
            if crc16_ccitt(body) != expected_crc:
                del self._buffer[0]
                continue

            frames.append(Frame(command=command, payload=payload, sequence=sequence))
            del self._buffer[:total]


@dataclass(frozen=True)
class CanFrame:
    bus: int
    can_id: int
    data: bytes
    flags: int = 0
    timestamp_ms: int = 0

    def pack(self) -> bytes:
        raw = bytes(self.data[:8]).ljust(8, b"\x00")
        return struct.pack(
            "<BIBB8sI",
            self.bus & 0xFF,
            self.can_id & 0xFFFFFFFF,
            self.flags & 0xFF,
            min(len(self.data), 8),
            raw,
            self.timestamp_ms & 0xFFFFFFFF,
        )

    @classmethod
    def unpack(cls, payload: bytes) -> "CanFrame":
        if len(payload) < 19:
            raise ValueError("CAN frame payload must be at least 19 bytes")
        bus, can_id, flags, dlc, raw, timestamp = struct.unpack_from("<BIBB8sI", payload)
        return cls(
            bus=bus,
            can_id=can_id,
            data=raw[: min(dlc, 8)],
            flags=flags,
            timestamp_ms=timestamp,
        )

    def display(self) -> str:
        data = " ".join(f"{byte:02X}" for byte in self.data)
        return f"CAN{self.bus + 1} 0x{self.can_id:03X} [{data}]"


def ping_frame(sequence: int = 1) -> Frame:
    return Frame(Command.PING, b"MOTOR_TUNER", sequence)


def stream_start_frame(enabled: bool = True, sequence: int = 0) -> Frame:
    command = Command.CAN_STREAM_START if enabled else Command.CAN_STREAM_STOP
    return Frame(command, b"", sequence)


def can_tx_frame(can_frame: CanFrame, sequence: int = 0) -> Frame:
    return Frame(Command.CAN_TX, can_frame.pack(), sequence)


def can_rx_frame(can_frame: CanFrame, sequence: int = 0) -> Frame:
    return Frame(Command.CAN_RX, can_frame.pack(), sequence)


def join_hex(data: Iterable[int]) -> str:
    return " ".join(f"{byte:02X}" for byte in data)
