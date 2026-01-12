# Copyright (c) 2026 Chanhyuk Jung
# SPDX-License-Identifier: MIT
#
# This file is part of a project licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import time
from dataclasses import dataclass, field
from typing import Generator, List, Optional, Tuple

from serial import Serial

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


def calc_checksum(packet: List[int]) -> int:
    return ~(sum(packet[2:]) & 0xFF) & 0xFF


def split_bytes(data: int, *, n_bytes: int = 2) -> List[int]:
    array = data.to_bytes(n_bytes, byteorder="little")
    return list(array)


def merge_bytes(array: List[int]) -> int:
    return int.from_bytes(array, byteorder="big")


class Params:
    def __init__(self, params: Optional[List[int]] = None) -> None:
        if params is None:
            params = []

        self.params = params

    def add(self, value: int, n_bytes: int = 1) -> None:
        self.params.extend(split_bytes(value, n_bytes=n_bytes))

    def parse_bytes(self) -> int:
        return merge_bytes(self.params)

    @property
    def raw(self) -> bytes:
        return bytes(self.params)


@dataclass(frozen=True)
class InstructionPacket:
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
    def raw(self) -> bytes:
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.instruction)
        packet.extend(self.params.raw)
        packet.extend(split_bytes(self.checksum))
        return bytes(packet)

    def __post_init__(self) -> None:
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

    def __init__(self, buffer: List[int]) -> None:
        self.header = (buffer[0], buffer[1])
        self.packet_id = buffer[2]
        self.length = buffer[3]
        self.error = buffer[4]
        self.params = Params(buffer[5:-1])
        self.checksum = buffer[-1]

    @property
    def raw(self) -> bytes:
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.error)
        packet.extend(self.params.raw)
        packet.append(self.checksum)
        return bytes(packet)

    @property
    def valid(self) -> bool:
        return calc_checksum(list(self.raw)[:-1]) == self.checksum


class Connection:
    def __init__(
        self, port: str, baudrate: int = 1_000_000, timeout: float = 1
    ) -> None:
        self.serial = Serial(baudrate=baudrate, timeout=timeout, write_timeout=timeout)

        self.serial.port = port

    def open(self) -> None:
        self.serial.open()

    def close(self) -> None:
        self.serial.close()

    def set_baudrate(self, baudrate: int) -> None:
        self.serial.baudrate = baudrate

    def read_header(self) -> List[int]:
        header = [0xFF, 0xFF]

        length = len(header)
        packet = []
        header_found = False
        t0 = time.time()
        while not header_found:
            packet.extend(list(self.serial.read(length - len(packet))))

            for _ in range(len(packet)):
                if packet[:length] == header:
                    header_found = True
                    break

                packet.pop(0)

            if self.serial.timeout is not None and time.time() - t0 >= (
                self.serial.timeout * length
            ):
                break

        return packet

    def read_packet(self) -> Optional[StatusPacket]:
        packet = self.read_header()

        if len(packet) < 2:
            return None

        buffer = list(self.serial.read(2))
        packet.extend(buffer)

        if len(buffer) < 2:
            return None

        _, length = buffer

        rest = list(self.serial.read(length))
        packet.extend(rest)

        if len(rest) < length:
            return None

        rx = StatusPacket(packet)

        return rx

    def stream_packets(
        self, count: Optional[int] = None
    ) -> Generator[Optional[StatusPacket], None, None]:
        if count is None:
            while True:
                yield self.read_packet()

        else:
            for _ in range(count):
                yield self.read_packet()

    def write_packet(self, tx: InstructionPacket) -> None:
        buffer = tx.raw

        count = 0
        while count < len(buffer):
            count = self.serial.write(buffer)
            buffer = buffer[count:]


class SyncParams(Params):
    def __init__(self, address: int, length: int) -> None:
        super().__init__()
        self.add(address)
        self.add(length)

        self.length = length
        self.num_motors = 0

    def add_value(self, dxl_id: int, value: int) -> None:
        self.add(dxl_id)
        self.add(value, self.length)

        self.num_motors += 1


class BulkParams(Params):
    def __init__(self) -> None:
        super().__init__([0x00])

        self.num_motors = 0

    def add_address(self, dxl_id: int, address: int, length: int) -> None:
        self.add(length)
        self.add(dxl_id)
        self.add(address)

        self.num_motors += 1


class MotorBus:
    def __init__(
        self, port: str, baudrate: int = 1_000_000, timeout: float = 0.1
    ) -> None:
        self.conn = Connection(port, baudrate, timeout=timeout)

    def connect(self) -> None:
        self.conn.open()

    def disconnect(self) -> None:
        self.conn.close()

    def set_baudrate(self, baudrate: int) -> None:
        self.conn.set_baudrate(baudrate)

    def ping(self, dxl_id: int) -> Response:
        tx = InstructionPacket(dxl_id, PING)
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        if not rx.valid or rx.error:
            return Response(error=rx.error, valid=rx.valid)

        return Response(error=0, valid=True, data=[])

    def read(self, dxl_id: int, address: int, length: int) -> Response:
        tx = InstructionPacket(dxl_id, READ, Params([address, length]))
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        if not rx.valid or rx.error:
            return Response(error=rx.error, valid=rx.valid)

        data = rx.params.parse_bytes()
        return Response(error=0, valid=True, data=data)

    def _write(
        self, dxl_id: int, instruction: int, address: int, length: int, value: int
    ) -> Optional[Response]:
        params = Params([address])
        params.add(value, length)

        tx = InstructionPacket(dxl_id, instruction, params)
        self.conn.write_packet(tx)

        if dxl_id == BROADCAST_ID:
            return None

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        return Response(error=rx.error, valid=rx.valid, data=[])

    def write(
        self, dxl_id: int, address: int, length: int, value: int
    ) -> Optional[Response]:
        return self._write(dxl_id, WRITE, address, length, value)

    def reg_write(
        self, dxl_id: int, address: int, length: int, value: int
    ) -> Optional[Response]:
        return self._write(dxl_id, REG_WRITE, address, length, value)

    def _send(
        self, dxl_id: int, instruction: int, buffer: Optional[List[int]] = None
    ) -> Response:
        if buffer is None:
            buffer = []

        params = Params(buffer)

        tx = InstructionPacket(dxl_id, instruction, params)
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        if not rx.valid or rx.error:
            return Response(error=rx.error, valid=rx.valid)

        return Response(error=rx.error, valid=rx.valid, data=[])

    def action(self) -> None:
        tx = InstructionPacket(BROADCAST_ID, ACTION)
        self.conn.write_packet(tx)

    def factory_reset(self, dxl_id: int) -> Response:
        assert dxl_id != BROADCAST_ID, (
            "Broadcast ID 0xFE is not allowed for factory_reset"
        )
        return self._send(dxl_id, FACTORY_RESET)

    def reboot(self, dxl_id: int) -> Response:
        return self._send(dxl_id, REBOOT)

    def sync_write(self, params: SyncParams) -> Response:
        assert params.num_motors > 0, "You need to add values with SyncParams.add_value"

        tx = InstructionPacket(BROADCAST_ID, SYNC_WRITE, params)
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        if not rx.valid or rx.error != 0:
            return Response(error=rx.error, valid=rx.valid)

        return Response(error=0, valid=True, data=[])

    def bulk_read(self, params: BulkParams) -> Response:
        assert params.num_motors > 0, (
            "You need to add addresses with SyncParams.add_address"
        )

        tx = InstructionPacket(BROADCAST_ID, BULK_READ, params)
        self.conn.write_packet(tx)

        data = []
        for rx in self.conn.stream_packets(count=params.num_motors):
            if rx is None:
                return Response(timeout=True)

            if not rx.valid or rx.error != 0:
                return Response(error=rx.error, valid=rx.valid)

            data.append(rx.params.parse_bytes())

        if len(data) == 0:
            return Response(timeout=True)

        return Response(error=0, valid=True, data=data)
