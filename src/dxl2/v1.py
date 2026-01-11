# Copyright (c) 2026 Chanhyuk Jung
# SPDX-License-Identifier: MIT
#
# This file is part of a project licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

from dataclasses import dataclass, field
from typing import List, Tuple

from .base import BaseConnection, BaseDriver, BasePacket, BaseParams
from .response import Response

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


def calc_checksum(packet):
    return ~(sum(packet[2:]) & 0xFF) & 0xFF


def split_bytes(data, *, n_bytes=2):
    array = data.to_bytes(n_bytes, byteorder="little")
    return list(array)


def merge_bytes(array):
    return int.from_bytes(array, byteorder="big")


class Params(BaseParams):
    def __init__(self, params=None):
        if params is None:
            params = []

        self.params = params

    def add(self, value, n_bytes=1):
        self.params.extend(split_bytes(value, n_bytes=n_bytes))

    def parse_bytes(self):
        return merge_bytes(self.params)

    @property
    def raw(self):
        return bytes(self.params)


@dataclass(frozen=True)
class InstructionPacket(BasePacket):
    packet_id: int
    instruction: int
    params: Params = field(default_factory=Params)

    header: List[int] = field(
        default_factory=lambda: [0xFF, 0xFF],
        init=False,
    )
    length: int = field(init=False)
    checksum: int = field(init=False)

    @property
    def raw(self):
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.instruction)
        packet.extend(self.params.raw)
        packet.extend(split_bytes(self.checksum))
        return bytes(packet)

    def __post_init__(self):
        object.__setattr__(self, "length", len(self.params.raw) + 2)

        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.extend(split_bytes(self.length))
        packet.append(self.instruction)
        packet.extend(self.params.raw)
        object.__setattr__(self, "checksum", calc_checksum(packet))


@dataclass
class StatusPacket:
    packet_id: int
    length: int
    error: int
    params: Params
    checksum: int

    header: Tuple[int, int]

    def __init__(self, buffer):
        buffer = list(buffer)

        self.header = tuple(buffer[:2])
        self.packet_id = buffer[2]
        self.length = buffer[3]
        self.error = buffer[4]
        self.params = Params(buffer[5:-1])
        self.checksum = buffer[-1]

    @property
    def raw(self):
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.error)
        packet.extend(self.params.raw)
        packet.append(self.checksum)
        return tuple(packet)

    @property
    def valid(self):
        return calc_checksum(list(self.raw)[:-1]) == self.checksum


class Connection(BaseConnection):
    def read_packet(self):
        packet = self.read_header([0xFF, 0xFF])

        if len(packet) < 2:
            return None

        buffer = list(self.read(2))
        packet.extend(buffer)

        if len(buffer) < 2:
            return None

        _, length = buffer

        rest = list(self.read(length))
        packet.extend(rest)

        if len(rest) < length:
            return None

        rx = StatusPacket(packet)

        return rx

    def write_packet(self, tx):
        buffer = tx.raw

        count = 0
        while count < len(buffer):
            count = self.write(buffer)
            buffer = buffer[count:]


class Driver(BaseDriver):
    def __init__(self, port, baudrate=1_000_000, timeout: float = 1):
        self.conn = Connection(port, baudrate, timeout)

    def connect(self):
        self.conn.open()

    def disconnect(self):
        self.conn.close()

    def ping(self, dxl_id):
        tx = InstructionPacket(dxl_id, PING)
        self.conn.write_packet(tx)

        r = Response.get(self.conn)
        return r

    def read(self, dxl_id, address, length):
        tx = InstructionPacket(dxl_id, READ, Params([address, length]))
        self.conn.write_packet(tx)

        r = Response.get(self.conn)

        if r.ok and r.data is not None:
            r.data = r.data.parse_bytes()

        return r

    def _write(self, dxl_id, instruction, address, length, value):
        params = Params([address])
        params.add(value, length)

        tx = InstructionPacket(dxl_id, instruction, params)
        self.conn.write_packet(tx)

        return Response.get(self.conn)

    def write(self, dxl_id, address, length, value):
        return self._write(dxl_id, WRITE, address, length, value)

    def reg_write(self, dxl_id, address, length, value):
        return self._write(dxl_id, REG_WRITE, address, length, value)

    def _send(self, dxl_id, instruction, params=None):
        if params is None:
            params = []

        params = Params(params)

        tx = InstructionPacket(dxl_id, instruction, params)
        self.conn.write_packet(tx)

        return Response.get(self.conn)

    def action(self):
        tx = InstructionPacket(BROADCAST_ID, ACTION)
        self.conn.write_packet(tx)

    def factory_reset(self, dxl_id):
        assert dxl_id < 0xFE
        return self._send(dxl_id, FACTORY_RESET)

    def reboot(self, dxl_id):
        return self._send(dxl_id, REBOOT)

    def sync_write(self, dxl_ids, address, length, values):
        params = Params([address, length])
        for dxl_id, value in zip(dxl_ids, values):
            params.add(dxl_id)
            params.add(value, length)

        tx = InstructionPacket(BROADCAST_ID, SYNC_WRITE, params)
        self.conn.write_packet(tx)

    def bulk_read(self, dxl_ids, addresses, lengths):
        params = Params([0x00])
        for dxl_id, address, length in zip(dxl_ids, addresses, lengths):
            params.add(length)
            params.add(dxl_id)
            params.add(address)

        tx = InstructionPacket(BROADCAST_ID, BULK_READ, params)
        self.conn.write_packet(tx)

        data = []
        r = None
        for r in Response.stream(self.conn, count=len(dxl_ids)):
            if r.ok and r.data is not None:
                data.append(r.data.parse_bytes())

        if r is None:
            return Response(timeout=True, corrupted=False)

        r.data = data
        return r
