# Copyright (c) 2026 Chanhyuk Jung
# SPDX-License-Identifier: MIT
#
# This file is part of a project licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import time
from dataclasses import dataclass, field, replace
from typing import List

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
SYNC_WRITE = 0x83
BULK_READ = 0x92


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

    @property
    def packet(self):
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.instruction)
        packet.extend(self.params)
        packet.append(self.checksum)
        return bytes(packet)

    def __post_init__(self):
        object.__setattr__(self, "length", len(self.params) + 2)

        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.instruction)
        packet.extend(self.params)

        object.__setattr__(self, "checksum", calc_checksum(packet))


@dataclass(frozen=True)
class StatusPacketV1:
    packet_id: int
    length: int
    error: int
    params: List[int]
    checksum: int

    header: List[int] = field(default_factory=lambda: [0xFF, 0xFF], init=False)

    @property
    def packet(self):
        packet = []
        packet.extend(self.header)
        packet.append(self.packet_id)
        packet.append(self.length)
        packet.append(self.error)
        packet.extend(self.params)
        packet.append(self.checksum)
        return tuple(packet)

    @property
    def valid(self):
        return calc_checksum(list(self.packet)[:-1]) == self.checksum


def transmit(ser, tx):
    buffer = tx.packet
    count = ser.write(buffer)

    if count < len(buffer):
        raise ConnectionError


def find_header(ser):
    packet = []
    header_found = False
    t0 = time.time()
    while not header_found:
        packet.extend(list(ser.read(2 - len(packet))))

        for _ in range(len(packet)):
            if packet[:2] == [0xFF, 0xFF]:
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

    buffer = list(ser.read(2))

    if len(buffer) < 2:
        return None

    packet_id, length = buffer

    rest = list(ser.read(length))

    if len(rest) < length:
        return None

    error = rest.pop(0)
    params = rest[:-1]
    checksum = rest[-1]

    rx = StatusPacketV1(packet_id, length, error, params, checksum)

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


def parse_bytes(r):
    return replace(r, data=merge_bytes(r.data))


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
        return get_response(self.serial, tx)

    def read(self, dxl_id, address, length):
        tx = InstructionPacketV1(dxl_id, READ, [address, length])
        r = get_response(self.serial, tx)

        if r.ok:
            r = parse_bytes(r)

        return r

    def _write(self, dxl_id, instruction, address, length, value):
        tx = InstructionPacketV1(
            dxl_id,
            instruction,
            [address, *split_bytes(value, n_bytes=length)],
        )

        return get_response(self.serial, tx)

    def write(self, dxl_id, address, length, value):
        return self._write(dxl_id, WRITE, address, length, value)

    def reg_write(self, dxl_id, address, length, value):
        return self._write(dxl_id, REG_WRITE, address, length, value)

    def _send(self, dxl_id, instruction, params=None):
        if params is None:
            params = []

        tx = InstructionPacketV1(dxl_id, instruction, params)

        return get_response(self.serial, tx)

    def action(self):
        tx = InstructionPacketV1(BROADCAST_ID, ACTION)

        transmit(self.serial, tx)

    def factory_reset(self, dxl_id):
        assert dxl_id < 0xFE
        return self._send(dxl_id, FACTORY_RESET)

    def reboot(self, dxl_id):
        return self._send(dxl_id, REBOOT)

    def sync_write(self, dxl_ids, address, length, values):
        params = [address, length]
        for dxl_id, value in zip(dxl_ids, values):
            params.append(dxl_id)
            params.extend(split_bytes(value, n_bytes=length))

        tx = InstructionPacketV1(BROADCAST_ID, SYNC_WRITE, params)

        transmit(self.serial, tx)

    def bulk_read(self, dxl_ids, addresses, lengths):
        params = [0x00]
        for dxl_id, address, length in zip(dxl_ids, addresses, lengths):
            params.append(length)
            params.append(dxl_id)
            params.append(address)

        tx = InstructionPacketV1(BROADCAST_ID, BULK_READ, params)

        data = []
        r = None
        for r in stream_response(self.serial, tx, count=len(dxl_ids)):
            if r.ok:
                data.append(parse_bytes(r).data)

        if r is None:
            return Response(timeout=True, corrupted=False)

        return replace(r, data=data)
