# Copyright (c) 2026 Chanhyuk Jung
# SPDX-License-Identifier: MIT
#
# This file is part of a project licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

import time

import serial


class BasePacket:
    @property
    def raw(self):
        raise NotImplementedError


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
        raise NotImplementedError


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


class BaseBus:
    def connect(self):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def __enter__(self):
        self.connect()

        return self

    def __exit__(self, *args):
        self.disconnect()
