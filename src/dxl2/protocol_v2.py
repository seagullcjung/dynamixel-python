# Copyright (c) 2026 Chanhyuk Jung
# SPDX-License-Identifier: MIT
#
# This file is part of a project licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import copy
import time
from dataclasses import dataclass, field, replace
from typing import List, Tuple

import serial

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


def split_bytes(data, *, n_bytes=2):
    array = data.to_bytes(n_bytes, byteorder="little")
    return list(array)


def merge_bytes(array):
    return int.from_bytes(array, byteorder="little")


def calc_crc_16(packet):
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


@dataclass(frozen=True)
class InstructionPacketV2:
    packet_id: int
    instruction: int
    params: List[int] = field(default_factory=list)

    header: List[int] = field(
        default_factory=lambda: [0xFF, 0xFF, 0xFD, 0x00],
        init=False,
    )
    length: int = field(init=False)
    crc: int = field(init=False)

    @property
    def packet(self):
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.extend(split_bytes(self.length))
        packet.append(self.instruction)
        packet.extend(self.params)
        packet.extend(split_bytes(self.crc))
        return bytes(packet)

    def __post_init__(self):
        object.__setattr__(self, "length", len(self.params) + 3)

        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.extend(split_bytes(self.length))
        packet.append(self.instruction)
        packet.extend(self.params)

        object.__setattr__(self, "crc", calc_crc_16(packet))

    def add_stuffing(self):
        packet = copy.deepcopy(self)

        params = packet.params
        indices = [
            i + 3
            for i in range(len(params) - 2)
            if params[i : i + 3] == [0xFF, 0xFF, 0xFD]
        ]

        for i in reversed(indices):
            params.insert(i, 0xFD)

        packet = replace(packet, params=params)
        return packet


class HardwareError(Exception):
    """Hardware error."""

    def __init__(self, dxl_id):
        message = (
            f"Alert! There is a hardware issue with device id: {dxl_id}. ",
            "Check the hardware error status value of the control table.",
        )
        super().__init__(message)


@dataclass(frozen=True)
class StatusPacketV2:
    packet_id: int
    length: int
    instruction: int
    error: int
    params: List[int]
    crc: int

    header: Tuple[int, int, int, int] = field(
        default_factory=lambda: (0xFF, 0xFF, 0xFD, 0x00),
        init=False,
    )

    @property
    def packet(self):
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.extend(split_bytes(self.length))
        packet.append(self.instruction)
        packet.append(self.error)
        packet.extend(self.params)
        packet.extend(split_bytes(self.crc))
        return bytes(packet)

    @property
    def valid(self):
        return calc_crc_16(list(self.packet)[:-2]) == self.crc

    def remove_stuffing(self):
        rx = copy.deepcopy(self)

        params = rx.params

        indices = [
            i + 3
            for i in range(len(params) - 3)
            if params[i : i + 4] == [0xFF, 0xFF, 0xFD, 0xFD]
        ]

        for i in reversed(indices):
            params.pop(i)

        rx = replace(rx, params=params)
        rx = replace(rx, crc=calc_crc_16(rx.packet[:-2]))
        return rx


def transmit(ser, tx):
    tx = tx.add_stuffing()
    buffer = tx.packet
    count = ser.write(buffer)

    if count < len(buffer):
        raise ConnectionError


def find_header(ser):
    packet = []
    header_found = False
    t0 = time.time()
    while not header_found:
        packet.extend(list(ser.read(4 - len(packet))))

        for _ in range(len(packet)):
            if packet[:4] == [0xFF, 0xFF, 0xFD, 0x00]:
                header_found = True
                break

            packet.pop(0)

        if ser.timeout is not None and time.time() - t0 >= ser.timeout:
            break

    return header_found


def receive(ser):
    found = find_header(ser)

    if not found:
        return None

    buffer = list(ser.read(3))

    if len(buffer) < 3:
        return None

    packet_id, length_l, length_h = buffer
    length = merge_bytes([length_l, length_h])

    rest = list(ser.read(length))

    if len(rest) < length:
        return None

    instruction = rest.pop(0)
    error = rest.pop(0)
    params = rest[:-2]
    crc = merge_bytes(rest[-2:])

    rx = StatusPacketV2(packet_id, length, instruction, error, params, crc)

    if rx.valid:
        rx = rx.remove_stuffing()

    if rx.error & 0x80:
        raise HardwareError(packet_id)

    return rx


def get_response(ser, tx):
    transmit(ser, tx)

    rx = receive(ser)
    if rx is None:
        r = Response(timeout=True, corrupted=False)

    elif not rx.valid:
        r = Response(timeout=False, corrupted=True)

    else:
        r = Response.from_rx(rx)

    return r


def stream_response(ser, tx, *, count=None):
    transmit(ser, tx)

    if count is None:
        while True:
            rx = receive(ser)

            if rx is None:
                yield Response(timeout=True, corrupted=False)
                break

            yield Response.from_rx(rx)

            if not rx.valid:
                break
    else:
        for _ in range(count):
            rx = receive(ser)

            if rx is None:
                yield Response(timeout=True, corrupted=False)
                break

            if not rx.valid:
                yield Response(timeout=False, corrupted=True)
                break

            yield Response.from_rx(rx)


def parse_ping(r):
    return replace(
        r,
        data={
            r.dxl_id: {
                "model_number": merge_bytes(r.data[:2]),
                "firmware_version": r.data[2],
            }
        },
    )


def parse_bytes(r):
    return replace(r, data=merge_bytes(r.data))


def parse_nested(r, lengths):
    packet = r.data[: lengths[0] + 1]

    data = []
    data.append(merge_bytes(packet[1:]))

    start = lengths[0] + 1
    for length in lengths[1:]:
        packet = r.data[start : start + length + 4]

        error = packet[2]
        if error & 0x80:
            packet_id = packet[3]
            raise HardwareError(packet_id)

        start += length + 4

        if (error & 0x07) != 0:
            return Response(timeout=False, corrupted=False, error=error, data=data)

        data.append(merge_bytes(packet[4:]))

    return replace(r, data=data)


class DynamixelSerialV2:
    def __init__(self, port, baudrate=1_000_000, timeout: float = 1):
        self.serial = serial.Serial(timeout=timeout, write_timeout=0)
        self.serial.port = port
        self.serial.baudrate = baudrate

    def set_buadrate(self, baudrate):
        self.serial.baudrate = baudrate

    def connect(self):
        self.serial.open()

    def disconnect(self):
        self.serial.close()

    def ping(self, dxl_id):
        tx = InstructionPacketV2(dxl_id, PING)
        r = get_response(self.serial, tx)

        if r.ok:
            r = parse_ping(r)

        return r

    def broadcast_ping(self):
        tx = InstructionPacketV2(BROADCAST_ID, PING)

        r = None
        data = {}
        for r in stream_response(self.serial, tx):
            if not r.ok:
                r = replace(r, data=data)
                break

            data.update(parse_ping(r).data)

        if r is None:
            return Response(timeout=True)

        r = replace(r, timeout=False, data=data)
        return r

    def read(self, dxl_id, address, length):
        params = []
        params.extend(split_bytes(address))
        params.extend(split_bytes(length))

        tx = InstructionPacketV2(dxl_id, READ, params)
        r = get_response(self.serial, tx)

        if r.ok:
            r = parse_bytes(r)

        return r

    def _write(self, dxl_id, instruction, address, length, value):
        tx = InstructionPacketV2(
            dxl_id,
            instruction,
            [*split_bytes(address), *split_bytes(value, n_bytes=length)],
        )
        return get_response(self.serial, tx)

    def write(self, dxl_id, address, length, value):
        return self._write(dxl_id, WRITE, address, length, value)

    def reg_write(self, dxl_id, address, length, value):
        return self._write(dxl_id, REG_WRITE, address, length, value)

    def _send(self, dxl_id, instruction, params=None):
        if params is None:
            params = []

        tx = InstructionPacketV2(dxl_id, instruction, params)
        return get_response(self.serial, tx)

    def action(self, dxl_id):
        return self._send(dxl_id, ACTION)

    def factory_reset(self, dxl_id):
        return self._send(dxl_id, FACTORY_RESET, [0xFF])

    def factory_reset_except_id(self, dxl_id):
        return self._send(dxl_id, FACTORY_RESET, [0x01])

    def factory_reset_except_id_baudrate(self, dxl_id):
        return self._send(dxl_id, FACTORY_RESET, [0x02])

    def reboot(self, dxl_id):
        return self._send(dxl_id, REBOOT)

    def clear_position(self, dxl_id):
        return self._send(dxl_id, CLEAR, [0x01, 0x44, 0x58, 0x4C, 0x22])

    def clear_errors(self, dxl_id):
        return self._send(dxl_id, CLEAR, [0x02, 0x45, 0x52, 0x43, 0x4C])

    def control_table_backup(self, dxl_id):
        return self._send(dxl_id, CONTROL_TABLE_BACKUP, [0x01, 0x43, 0x54, 0x52, 0x4C])

    def control_table_restore(self, dxl_id):
        return self._send(dxl_id, CONTROL_TABLE_BACKUP, [0x02, 0x43, 0x54, 0x52, 0x4C])

    def _sync_read(self, tx, dxl_ids):
        data = []
        r = None
        for r in stream_response(self.serial, tx, count=len(dxl_ids)):
            if r.ok:
                data.append(parse_bytes(r).data)

        if r is None:
            return Response(timeout=True, corrupted=False)

        return replace(r, data=data)

    def sync_read(self, dxl_ids, address, length):
        params = []
        params.extend(split_bytes(address))
        params.extend(split_bytes(length))
        params.extend(dxl_ids)

        tx = InstructionPacketV2(BROADCAST_ID, SYNC_READ, params)

        return self._sync_read(tx, dxl_ids)

    def sync_write(self, dxl_ids, address, length, values):
        params = []
        params.extend(split_bytes(address))
        params.extend(split_bytes(length))

        for dxl_id, value in zip(dxl_ids, values):
            params.append(dxl_id)
            params.extend(split_bytes(value, n_bytes=length))

        tx = InstructionPacketV2(BROADCAST_ID, SYNC_WRITE, params)

        transmit(self.serial, tx)

    def fast_sync_read(self, dxl_ids, address, length):
        params = []
        params.extend(split_bytes(address))
        params.extend(split_bytes(length))
        params.extend(dxl_ids)

        tx = InstructionPacketV2(BROADCAST_ID, FAST_SYNC_READ, params)

        r = get_response(self.serial, tx)

        if r.ok:
            r = parse_nested(r, [length] * len(dxl_ids))

        return r

    def bulk_read(self, dxl_ids, addresses, lengths):
        params = []
        for dxl_id, address, length in zip(dxl_ids, addresses, lengths):
            params.append(dxl_id)
            params.extend(split_bytes(address))
            params.extend(split_bytes(length))

        tx = InstructionPacketV2(BROADCAST_ID, BULK_READ, params)

        return self._sync_read(tx, dxl_ids)

    def bulk_write(self, dxl_ids, addresses, lengths, values):
        params = []
        for dxl_id, address, length, value in zip(dxl_ids, addresses, lengths, values):
            params.append(dxl_id)
            params.extend(split_bytes(address))
            params.extend(split_bytes(length))
            params.extend(split_bytes(value, n_bytes=length))

        tx = InstructionPacketV2(BROADCAST_ID, BULK_WRITE, params)

        transmit(self.serial, tx)

    def fast_bulk_read(self, dxl_ids, addresses, lengths):
        params = []
        for dxl_id, address, length in zip(dxl_ids, addresses, lengths):
            params.append(dxl_id)
            params.extend(split_bytes(address))
            params.extend(split_bytes(length))

        tx = InstructionPacketV2(BROADCAST_ID, FAST_BULK_READ, params)

        r = get_response(self.serial, tx)

        if r.ok:
            r = parse_nested(r, lengths)

        return r
