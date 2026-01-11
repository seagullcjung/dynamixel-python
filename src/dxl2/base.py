# Copyright (c) 2026 Chanhyuk Jung
# SPDX-License-Identifier: MIT
#
# This file is part of a project licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import time
from dataclasses import dataclass
from typing import Any, Optional

import serial


class BaseConnection(serial.Serial):
    def __init__(self, port, baudrate=1_000_000, timeout: float = 1):
        super().__init__(baudrate=baudrate, timeout=timeout, write_timeout=timeout)

        self.port = port

    def read_header(self, header):
        length = len(header)
        packet = []
        header_found = False
        t0 = time.time()
        while not header_found:
            packet.extend(list(self.read(length - len(packet))))

            for _ in range(len(packet)):
                if packet[:length] == header:
                    header_found = True
                    break

                packet.pop(0)

            if self.timeout is not None and time.time() - t0 >= (self.timeout * length):
                break

        return packet

    def read_packet(self):
        raise NotImplementedError

    def stream_packets(self, count=None):
        if count is None:
            while True:
                yield self.read_packet()

        else:
            for _ in range(count):
                yield self.read_packet()

    def write_packet(self, tx):
        tx.add_stuffing()
        buffer = tx.raw

        count = 0
        while count < len(buffer):
            count = self.write(buffer)
            buffer = buffer[count:]


@dataclass
class Response:
    timeout: Optional[bool] = None
    corrupted: Optional[bool] = None

    error: Optional[int] = None
    dxl_id: Optional[int] = None
    data: Optional[Any] = None

    @classmethod
    def from_rx(cls, rx):
        return cls(
            timeout=False,
            corrupted=not rx.valid,
            error=rx.error,
            dxl_id=rx.packet_id,
            data=rx.params,
        )

    @property
    def ok(self):
        ok = not self.timeout and not self.corrupted
        if self.error is None:
            return ok

        return ok and self.error == 0

    @classmethod
    def get(cls, dxl):
        rx = dxl.read_packet()

        if rx is None:
            r = cls(timeout=True, corrupted=False)

        elif not rx.valid:
            r = cls(timeout=False, corrupted=True)

        else:
            r = cls.from_rx(rx)

        return r

    @classmethod
    def stream(cls, dxl, count=None):
        for rx in dxl.stream_packets(count):
            if rx is None:
                yield cls(timeout=True, corrupted=False)
                break

            yield cls.from_rx(rx)

            if not rx.valid:
                break


class BaseParams:
    def __init__(self, params=None):
        if params is None:
            params = []

        self.params = params

    def add(self, value, n_bytes=1):
        raise NotImplementedError

    @property
    def raw(self):
        return bytes(self.params)


class BaseDriver:
    def connect(self):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def __enter__(self):
        self.connect()

        return self

    def __exit__(self, *args):
        self.disconnect()
