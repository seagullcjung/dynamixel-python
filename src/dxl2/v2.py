# Copyright (c) 2026 Chanhyuk Jung
# SPDX-License-Identifier: MIT
#
# This file is part of a project licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Generator, List, Optional, Tuple

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
CLEAR = 0x10
CONTROL_TABLE_BACKUP = 0x20
SYNC_READ = 0x82
SYNC_WRITE = 0x83
FAST_SYNC_READ = 0x8A
BULK_READ = 0x92
BULK_WRITE = 0x93
FAST_BULK_READ = 0x9A


def split_bytes(data: int, *, n_bytes: int = 2, signed: bool = False) -> List[int]:
    array = data.to_bytes(n_bytes, byteorder="little", signed=signed)
    return list(array)


def merge_bytes(array: List[int], signed: bool = False) -> int:
    return int.from_bytes(array, byteorder="little", signed=signed)


def calc_crc_16(packet: List[int]) -> int:
    crc_table = [
        0x0000, 0x8005, 0x800F, 0x000A, 0x801B, 0x001E, 0x0014, 0x8011,
        0x8033, 0x0036, 0x003C, 0x8039, 0x0028, 0x802D, 0x8027, 0x0022,
        0x8063, 0x0066, 0x006C, 0x8069, 0x0078, 0x807D, 0x8077, 0x0072,
        0x0050, 0x8055, 0x805F, 0x005A, 0x804B, 0x004E, 0x0044, 0x8041,
        0x80C3, 0x00C6, 0x00CC, 0x80C9, 0x00D8, 0x80DD, 0x80D7, 0x00D2,
        0x00F0, 0x80F5, 0x80FF, 0x00FA, 0x80EB, 0x00EE, 0x00E4, 0x80E1,
        0x00A0, 0x80A5, 0x80AF, 0x00AA, 0x80BB, 0x00BE, 0x00B4, 0x80B1,
        0x8093, 0x0096, 0x009C, 0x8099, 0x0088, 0x808D, 0x8087, 0x0082,
        0x8183, 0x0186, 0x018C, 0x8189, 0x0198, 0x819D, 0x8197, 0x0192,
        0x01B0, 0x81B5, 0x81BF, 0x01BA, 0x81AB, 0x01AE, 0x01A4, 0x81A1,
        0x01E0, 0x81E5, 0x81EF, 0x01EA, 0x81FB, 0x01FE, 0x01F4, 0x81F1,
        0x81D3, 0x01D6, 0x01DC, 0x81D9, 0x01C8, 0x81CD, 0x81C7, 0x01C2,
        0x0140, 0x8145, 0x814F, 0x014A, 0x815B, 0x015E, 0x0154, 0x8151,
        0x8173, 0x0176, 0x017C, 0x8179, 0x0168, 0x816D, 0x8167, 0x0162,
        0x8123, 0x0126, 0x012C, 0x8129, 0x0138, 0x813D, 0x8137, 0x0132,
        0x0110, 0x8115, 0x811F, 0x011A, 0x810B, 0x010E, 0x0104, 0x8101,
        0x8303, 0x0306, 0x030C, 0x8309, 0x0318, 0x831D, 0x8317, 0x0312,
        0x0330, 0x8335, 0x833F, 0x033A, 0x832B, 0x032E, 0x0324, 0x8321,
        0x0360, 0x8365, 0x836F, 0x036A, 0x837B, 0x037E, 0x0374, 0x8371,
        0x8353, 0x0356, 0x035C, 0x8359, 0x0348, 0x834D, 0x8347, 0x0342,
        0x03C0, 0x83C5, 0x83CF, 0x03CA, 0x83DB, 0x03DE, 0x03D4, 0x83D1,
        0x83F3, 0x03F6, 0x03FC, 0x83F9, 0x03E8, 0x83ED, 0x83E7, 0x03E2,
        0x83A3, 0x03A6, 0x03AC, 0x83A9, 0x03B8, 0x83BD, 0x83B7, 0x03B2,
        0x0390, 0x8395, 0x839F, 0x039A, 0x838B, 0x038E, 0x0384, 0x8381,
        0x0280, 0x8285, 0x828F, 0x028A, 0x829B, 0x029E, 0x0294, 0x8291,
        0x82B3, 0x02B6, 0x02BC, 0x82B9, 0x02A8, 0x82AD, 0x82A7, 0x02A2,
        0x82E3, 0x02E6, 0x02EC, 0x82E9, 0x02F8, 0x82FD, 0x82F7, 0x02F2,
        0x02D0, 0x82D5, 0x82DF, 0x02DA, 0x82CB, 0x02CE, 0x02C4, 0x82C1,
        0x8243, 0x0246, 0x024C, 0x8249, 0x0258, 0x825D, 0x8257, 0x0252,
        0x0270, 0x8275, 0x827F, 0x027A, 0x826B, 0x026E, 0x0264, 0x8261,
        0x0220, 0x8225, 0x822F, 0x022A, 0x823B, 0x023E, 0x0234, 0x8231,
        0x8213, 0x0216, 0x021C, 0x8219, 0x0208, 0x820D, 0x8207, 0x0202,
    ]  # fmt: skip

    crc = 0
    for byte in packet:
        i = ((crc >> 8) ^ byte) & 0xFF
        crc = (crc << 8) ^ crc_table[i]
        crc = crc & 0xFFFF

    return crc


class Params:
    def __init__(self, params: Optional[List[int]] = None) -> None:
        if params is None:
            params = []

        self.params = params

    def add(self, value: int, n_bytes: int = 1, signed: bool = False) -> None:
        self.params.extend(split_bytes(value, n_bytes=n_bytes, signed=signed))

    def parse_ping(self) -> Dict[str, int]:
        return {
            "model_number": merge_bytes(self.params[:2]),
            "firmware_version": self.params[2],
        }

    def parse_bytes(self, signed: bool) -> int:
        return merge_bytes(self.params, signed=signed)

    def parse_nested(self, lengths: List[int], signs: List[bool]) -> List[int]:
        packet = self.params[: lengths[0] + 1]

        data = []
        data.append(merge_bytes(packet[1:], signs[0]))

        start = lengths[0] + 1
        for length, sign in zip(lengths[1:], signs[1:]):
            packet = self.params[start : start + length + 4]

            error = packet[2]
            if error & 0x80:
                packet_id = packet[3]
                raise HardwareError(packet_id)

            start += length + 4

            data.append(merge_bytes(packet[4:], sign))

        return data

    @property
    def raw(self) -> bytes:
        return bytes(self.params)


def add_stuffing(params: Params) -> Params:
    buffer = list(params.raw)
    indices = [
        i + 3 for i in range(len(buffer) - 2) if buffer[i : i + 3] == [0xFF, 0xFF, 0xFD]
    ]

    for i in reversed(indices):
        buffer.insert(i, 0xFD)

    return Params(buffer)


@dataclass(frozen=True)
class InstructionPacket:
    packet_id: int
    instruction: int
    params: Params = field(default_factory=Params)

    header: List[int] = field(
        default_factory=lambda: [0xFF, 0xFF, 0xFD, 0x00],
        init=False,
    )
    length: int = field(init=False)
    crc: int = field(init=False)

    @property
    def raw(self) -> bytes:
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.extend(split_bytes(self.length))
        packet.append(self.instruction)
        packet.extend(self.params.raw)
        packet.extend(split_bytes(self.crc))
        return bytes(packet)

    def __post_init__(self) -> None:
        object.__setattr__(self, "length", len(self.params.raw) + 3)

        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.extend(split_bytes(self.length))
        packet.append(self.instruction)
        params = add_stuffing(self.params)
        packet.extend(params.raw)
        object.__setattr__(self, "crc", calc_crc_16(packet))


@dataclass
class StatusPacket:
    header: Tuple[int, int, int, int]
    packet_id: int
    length: int
    instruction: int
    error: int
    params: Params
    crc: int

    def __init__(self, buffer: List[int]) -> None:
        self.header = (buffer[0], buffer[1], buffer[2], buffer[3])
        self.packet_id = buffer[4]
        self.length = merge_bytes(buffer[5:7])
        self.instruction, self.error = buffer[7:9]
        self.params = Params(buffer[9:-2])
        self.crc = merge_bytes(buffer[-2:])

    @property
    def raw(self) -> bytes:
        packet: List[int] = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.extend(split_bytes(self.length))
        packet.append(self.instruction)
        packet.append(self.error)
        packet.extend(self.params.raw)
        packet.extend(split_bytes(self.crc))
        return bytes(packet)

    @property
    def valid(self) -> bool:
        return calc_crc_16(list(self.raw)[:-2]) == self.crc

    def remove_stuffing(self) -> None:
        params = list(self.params.raw)

        indices = [
            i + 3
            for i in range(len(params) - 3)
            if params[i : i + 4] == [0xFF, 0xFF, 0xFD, 0xFD]
        ]

        for i in reversed(indices):
            params.pop(i)

        self.params = Params(params)
        self.crc = calc_crc_16(list(self.raw)[:-2])


class HardwareError(Exception):
    """Hardware error."""


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
        header = [0xFF, 0xFF, 0xFD, 0x00]

        length = len(header)
        packet: List[int] = []
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

        if len(packet) < 4:
            return None

        buffer = list(self.serial.read(3))
        packet.extend(buffer)

        if len(buffer) < 3:
            return None

        packet_id, length_l, length_h = buffer
        length = merge_bytes([length_l, length_h])

        rest = list(self.serial.read(length))
        packet.extend(rest)

        if len(rest) < length:
            return None

        rx = StatusPacket(packet)

        if rx.error & 0x80:
            msg = (
                f"Alert! There is a hardware issue with device id: {packet_id}. ",
                "Check the hardware error status value of the control table.",
            )
            raise HardwareError(msg)

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


class SyncType(Enum):
    READ = 0
    WRITE = 1


class SyncParams(Params):
    def __init__(self, address: int, length: int, signed: bool = False) -> None:
        super().__init__()
        self.add(address, 2)
        self.add(length, 2)

        self.length = length
        self.num_motors = 0
        self.signed = signed

        self.type: Optional[SyncType] = None

    def add_motor(self, dxl_id: int) -> None:
        if self.type is None:
            self.type = SyncType.READ
        else:
            assert self.type == SyncType.READ, "You can't mix add_motor and add_value"

        self.add(dxl_id)
        self.num_motors += 1

    def add_value(self, dxl_id: int, value: int) -> None:
        if self.type is None:
            self.type = SyncType.WRITE
        else:
            assert self.type == SyncType.WRITE, "You can't mix add_motor and add_value"

        self.add(dxl_id)
        self.add(value, self.length, self.signed)

        self.num_motors += 1


class BulkType(Enum):
    READ = 0
    WRITE = 1


class BulkParams(Params):
    def __init__(self) -> None:
        super().__init__()

        self.num_motors = 0
        self.type: Optional[BulkType] = None

        self.lengths: List[int] = []
        self.signs: List[bool] = []

    def add_address(
        self, dxl_id: int, address: int, length: int, signed: bool = False
    ) -> None:
        if self.type is None:
            self.type = BulkType.READ
        else:
            assert self.type == BulkType.READ, "You can't mix add_address and add_value"

        self.add(dxl_id)
        self.add(address, 2)
        self.add(length, 2)

        self.num_motors += 1
        self.lengths.append(length)
        self.signs.append(signed)

    def add_value(
        self, dxl_id: int, address: int, length: int, value: int, signed: bool = False
    ) -> None:
        if self.type is None:
            self.type = BulkType.WRITE
        else:
            assert self.type == BulkType.WRITE, (
                "You can't mix add_address and add_value"
            )

        self.add(dxl_id)
        self.add(address, 2)
        self.add(length, 2)
        self.add(value, length, signed)

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

    def scan(
        self, baudrates: Optional[List[int]] = None
    ) -> List[Dict[int, Dict[str, int]]]:
        if baudrates is None:
            baudrates = [
                9600,
                57600,
                115200,
                1_000_000,
                2_000_000,
                3_000_000,
                4_000_000,
                4_500_000,
                6_000_000,
                10_500_000,
            ]

        motors = []

        for baudrate in baudrates:
            self.set_baudrate(baudrate)

            for dxl_id in range(0, 0xFE):
                r = self.ping(dxl_id)

                if r.ok and r.data is not None:
                    info = r.data
                    info["baudrate"] = baudrate
                    motors.append({dxl_id: info})

        return motors

    def ping(self, dxl_id: int) -> Response:
        tx = InstructionPacket(dxl_id, PING)
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        if not rx.valid or rx.error:
            return Response(error=rx.error, valid=rx.valid)

        if rx.valid:
            rx.remove_stuffing()

        data = rx.params.parse_ping()
        return Response(error=0, valid=True, data=data)

    def broadcast_ping(self) -> Response:
        tx = InstructionPacket(BROADCAST_ID, PING)
        self.conn.write_packet(tx)

        r = None

        data = {}
        for rx in self.conn.stream_packets():
            if rx is None:
                break

            r = Response(error=rx.error, valid=rx.valid)

            if r.ok:
                if not rx.valid or rx.error:
                    return Response(error=rx.error, valid=rx.valid)

                if rx.valid:
                    rx.remove_stuffing()

                data.update({rx.packet_id: rx.params.parse_ping()})
            else:
                break

        if r is None:
            return Response(timeout=True)

        r.data = data
        return r

    def read(
        self, dxl_id: int, address: int, length: int, signed: bool = False
    ) -> Response:
        params = Params()
        params.add(address, 2)
        params.add(length, 2)

        tx = InstructionPacket(dxl_id, READ, params)
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        if not rx.valid or rx.error:
            return Response(error=rx.error, valid=rx.valid)

        if rx.valid:
            rx.remove_stuffing()

        data = rx.params.parse_bytes(signed)
        return Response(error=0, valid=True, data=data)

    def _write(
        self,
        dxl_id: int,
        instruction: int,
        address: int,
        length: int,
        value: int,
        signed: bool,
    ) -> Response:
        params = Params()
        params.add(address, 2)
        params.add(value, length, signed)

        tx = InstructionPacket(dxl_id, instruction, params)
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        return Response(error=rx.error, valid=rx.valid, data=[])

    def write(
        self, dxl_id: int, address: int, length: int, value: int, signed: bool = False
    ) -> Response:
        return self._write(dxl_id, WRITE, address, length, value, signed)

    def reg_write(
        self, dxl_id: int, address: int, length: int, value: int, signed: bool = False
    ) -> Response:
        return self._write(dxl_id, REG_WRITE, address, length, value, signed)

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

        if rx.valid:
            rx.remove_stuffing()

        return Response(error=rx.error, valid=rx.valid, data=[])

    def action(self, dxl_id: int) -> Response:
        return self._send(dxl_id, ACTION)

    def factory_reset(self, dxl_id: int) -> Response:
        assert dxl_id != BROADCAST_ID
        return self._send(dxl_id, FACTORY_RESET, [0xFF])

    def factory_reset_except_id(self, dxl_id: int) -> Response:
        return self._send(dxl_id, FACTORY_RESET, [0x01])

    def factory_reset_except_id_baudrate(self, dxl_id: int) -> Response:
        return self._send(dxl_id, FACTORY_RESET, [0x02])

    def reboot(self, dxl_id: int) -> Response:
        return self._send(dxl_id, REBOOT)

    def clear_position(self, dxl_id: int) -> Response:
        return self._send(dxl_id, CLEAR, [0x01, 0x44, 0x58, 0x4C, 0x22])

    def clear_errors(self, dxl_id: int) -> Response:
        return self._send(dxl_id, CLEAR, [0x02, 0x45, 0x52, 0x43, 0x4C])

    def control_table_backup(self, dxl_id: int) -> Response:
        return self._send(dxl_id, CONTROL_TABLE_BACKUP, [0x01, 0x43, 0x54, 0x52, 0x4C])

    def control_table_restore(self, dxl_id: int) -> Response:
        return self._send(dxl_id, CONTROL_TABLE_BACKUP, [0x02, 0x43, 0x54, 0x52, 0x4C])

    def _sync_read(
        self, tx: InstructionPacket, count: int, signs: List[bool]
    ) -> Response:
        self.conn.write_packet(tx)

        data = []
        for rx, signed in zip(self.conn.stream_packets(count=count), signs):
            if rx is None:
                return Response(timeout=True)

            if not rx.valid or rx.error != 0:
                return Response(error=rx.error, valid=rx.valid)

            if rx.valid:
                rx.remove_stuffing()

            data.append(rx.params.parse_bytes(signed))

        if len(data) == 0:
            return Response(timeout=True)

        return Response(error=0, valid=True, data=data)

    def sync_read(self, params: SyncParams) -> Response:
        assert params.num_motors > 0, "You need to add motors with SyncParams.add_motor"

        tx = InstructionPacket(BROADCAST_ID, SYNC_READ, params)

        return self._sync_read(
            tx, params.num_motors, [params.signed] * params.num_motors
        )

    def sync_write(self, params: SyncParams) -> None:
        assert params.num_motors > 0, "You need to add values with SyncParams.add_value"

        tx = InstructionPacket(BROADCAST_ID, SYNC_WRITE, params)
        self.conn.write_packet(tx)

    def fast_sync_read(self, params: SyncParams, signed: bool = False) -> Response:
        assert params.num_motors > 0, "You need to add motors with SyncParams.add_motor"

        tx = InstructionPacket(BROADCAST_ID, FAST_SYNC_READ, params)
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        if not rx.valid or rx.error != 0:
            return Response(error=rx.error, valid=rx.valid)

        if rx.valid:
            rx.remove_stuffing()

        data = rx.params.parse_nested(
            [params.length] * params.num_motors, [signed] * params.num_motors
        )
        return Response(error=0, valid=True, data=data)

    def bulk_read(self, params: BulkParams) -> Response:
        assert params.num_motors > 0 and params.type == BulkType.READ, (
            "You need to add addresses with BulkParams.ad_address"
        )

        tx = InstructionPacket(BROADCAST_ID, BULK_READ, params)
        return self._sync_read(tx, params.num_motors, params.signs)

    def bulk_write(self, params: BulkParams) -> None:
        assert params.num_motors > 0 and params.type == BulkType.WRITE, (
            "You need to add values with BulkParams.add_value"
        )

        tx = InstructionPacket(BROADCAST_ID, BULK_WRITE, params)
        self.conn.write_packet(tx)

    def fast_bulk_read(self, params: BulkParams) -> Response:
        assert params.num_motors > 0 and params.type == BulkType.READ, (
            "You need to add addresses with BulkParams.ad_address"
        )

        tx = InstructionPacket(BROADCAST_ID, FAST_BULK_READ, params)
        self.conn.write_packet(tx)

        rx = self.conn.read_packet()

        if rx is None:
            return Response(timeout=True)

        if not rx.valid or rx.error != 0:
            return Response(error=rx.error, valid=rx.valid)

        if rx.valid:
            rx.remove_stuffing()

        data = rx.params.parse_nested(params.lengths, params.signs)
        return Response(error=0, valid=True, data=data)
