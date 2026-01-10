# Copyright (c) 2026 Chanhyuk Jung
# SPDX-License-Identifier: MIT
#
# This file is part of a project licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import logging
import time
from dataclasses import dataclass, field, replace
from typing import Any, List, Optional

import serial

BROADCAST_ID = 0xFE

PING = 0x01
READ = 0x02
WRITE = 0x03
REG_WRITE = 0x04
ACTION = 0x05
FACTORY_RESET = 0x06
REBOOT = 0x08
SYNC_WRITE = 0x83
BULK_READ = 0x92


error_msgs = [
    "The applied voltage is out of the range of operating voltage set in the Control table.",
    "Goal Position is written out of the range from CW Angle Limit to CCW Angle Limit.",
    "Internal temperature of DYNAMIXEL is out of the range of operating temperature set in the Control table.",
    "An instruction is out of the range for use.",
    "Checksum of the transmitted Instruction Packet is incorrect.",
    "The current load cannot be controlled by the set Torque.",
    "An undefined instruction or delivering the action instruction without the Reg Write instruction.",
]

logger = logging.getLogger(__name__)


def calc_checksum(packet):
    return ~(sum(packet[2:]) & 0xFF) & 0xFF


def split_bytes(data, *, n_bytes=2):
    array = data.to_bytes(n_bytes, byteorder="little")
    return list(array)


def merge_bytes(array):
    return int.from_bytes(array, byteorder="big")


@dataclass(frozen=True)
class InstructionPacketV1:
    packet_id: int
    instruction: int
    params: List[int] = field(default_factory=list)

    header: List[int] = field(default_factory=lambda: [0xFF, 0xFF], init=False)
    length: int = field(init=False)
    checksum: int = field(init=False)

    def as_tuple(self):
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.instruction)
        packet.extend(self.params)
        packet.append(self.checksum)
        return tuple(packet)

    def __post_init__(self):
        object.__setattr__(self, "length", len(self.params) + 2)

        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.instruction)
        packet.extend(self.params)

        object.__setattr__(self, "checksum", calc_checksum(packet))

    def write_to(self, ser):
        to_write = bytes(self.as_tuple())

        written_bytes = ser.write(to_write)

        return written_bytes == len(to_write)


@dataclass(frozen=True)
class StatusPacketV1:
    packet_id: int
    length: int
    error: int
    params: List[int]
    checksum: int

    header: List[int] = field(default_factory=lambda: [0xFF, 0xFF], init=False)

    def as_tuple(self):
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.error)
        packet.extend(self.params)
        packet.append(self.checksum)
        return tuple(packet)

    def is_valid(self):
        return calc_checksum(self.as_tuple()[:-1]) == self.checksum

    @classmethod
    def read_from(cls, ser):
        packet = []
        header_found = False
        t0 = time.time()
        while not header_found:
            # Header1 Header2 Packet ID Length
            packet.extend(list(ser.read(4 - len(packet))))

            for _ in range(len(packet)):
                if packet[:2] == [0xFF, 0xFF]:
                    header_found = True
                    break

                packet.pop(0)

            if ser.timeout is not None and time.time() - t0 >= ser.timeout:
                break

        if not header_found:
            return None

        if len(packet) < 4:
            packet.extend(ser.read(4 - len(packet)))

        if len(packet) < 4:
            return None

        packet_id = packet[2]
        length = packet[3]

        rest = list(ser.read(length))
        if len(rest) < length:
            return None

        packet.extend(rest)

        error = packet[4]
        if error:
            msg = [f"Error on dxl_id {packet_id}:"]

            mask = 0x02
            for error_msg in error_msgs:
                if error & mask:
                    msg.append(error_msg)

                mask <<= 1

            logger.error(" ".join(msg))

        params = packet[5:-1]

        checksum = packet[-1]

        rx = cls(packet_id, length, error, params, checksum)

        return rx


@dataclass(frozen=True)
class Status:
    packet: StatusPacketV1
    error_number: int = field(init=False)
    valid: bool = field(init=False)
    data: Optional[Any] = None

    def __post_init__(self):
        object.__setattr__(self, "error_number", self.packet.error)
        object.__setattr__(self, "valid", self.packet.is_valid())

    def is_ok(self):
        return self.valid and self.error_number == 0

    @classmethod
    def parse_bytes(cls, rx: StatusPacketV1):
        return cls(rx, merge_bytes(rx.params))


class DynamixelSerialV1:
    def __init__(self, port, baudrate=1_000_000, timeout: float = 1):
        self.serial = serial.Serial(timeout=timeout, write_timeout=0)
        self.serial.port = port
        self.serial.baudrate = baudrate

    def connect(self):
        self.serial.open()

    def disconnect(self):
        self.serial.close()

    def set_buadrate(self, baudrate):
        self.serial.baudrate = baudrate

    def ping(self, dxl_id):
        tx = InstructionPacketV1(dxl_id, PING)
        ok = tx.write_to(self.serial)

        if not ok:
            return False

        rx = StatusPacketV1.read_from(self.serial)

        if rx is None:
            return False

        status = Status(rx)
        return status.is_ok()

    def read(self, dxl_id, address, length):
        tx = InstructionPacketV1(dxl_id, READ, [address, length])
        ok = tx.write_to(self.serial)

        if not ok:
            return None

        rx = StatusPacketV1.read_from(self.serial)

        if rx is None:
            return None

        status = Status.parse_bytes(rx)

        if not status.is_ok():
            return None

        return status.data

    def _write(self, dxl_id, instruction, address, length, value):
        tx = InstructionPacketV1(
            dxl_id,
            instruction,
            [address, *split_bytes(value, n_bytes=length)],
        )
        ok = tx.write_to(self.serial)

        if not ok:
            return False

        rx = StatusPacketV1.read_from(self.serial)

        if rx is None:
            return False

        status = Status(rx)
        return status.is_ok()

    def write(self, dxl_id, address, length, value):
        return self._write(dxl_id, WRITE, address, length, value)

    def reg_write(self, dxl_id, address, length, value):
        return self._write(dxl_id, REG_WRITE, address, length, value)

    def _send(self, dxl_id, instruction, params=None):
        if params is None:
            params = []

        tx = InstructionPacketV1(dxl_id, instruction, params)
        ok = tx.write_to(self.serial)

        if not ok:
            return False

        rx = StatusPacketV1.read_from(self.serial)

        if rx is None:
            return False

        status = Status(rx)
        return status.is_ok()

    def action(self):
        tx = InstructionPacketV1(BROADCAST_ID, ACTION)
        ok = tx.write_to(self.serial)

        return ok

    def factory_reset(self, dxl_id):
        assert dxl_id < 0xFE
        return self._send(dxl_id, FACTORY_RESET)

    def reboot(self, dxl_id):
        return self._send(dxl_id, REBOOT)

    def sync_write(self, dxl_ids, address, length, values):
        tx = InstructionPacketV1(BROADCAST_ID, SYNC_WRITE, [address, length])

        params = tx.params
        for dxl_id, value in zip(dxl_ids, values):
            params.append(dxl_id)
            params.extend(split_bytes(value, n_bytes=length))

        tx = replace(tx, params=params)
        ok = tx.write_to(self.serial)

        return ok

    def bulk_read(self, dxl_ids, addresses, lengths):
        params = [0x00]
        for dxl_id, address, length in zip(dxl_ids, addresses, lengths):
            params.append(length)
            params.append(dxl_id)
            params.append(address)

        tx = InstructionPacketV1(BROADCAST_ID, BULK_READ, params)
        ok = tx.write_to(self.serial)

        if not ok:
            return None

        data = []
        for _ in dxl_ids:
            rx = StatusPacketV1.read_from(self.serial)

            if rx is None:
                return None

            status = Status.parse_bytes(rx)

            if not status.is_ok():
                return None

            data.append(status.data)

        return data
