import pytest
from serial import Serial

from dxl2.v1 import BulkParams, Connection, MotorBus, SyncParams, calc_checksum

TIMEOUT = 0.01


ID = 0x01
INST = 0x01
PARAMS = [0x01]
ERROR = 0x00

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


def build_tx(packet_id=ID, instruction=INST, params=PARAMS):
    packet = [0xFF, 0xFF]
    packet.append(packet_id)
    packet.append(len(params) + 2)
    packet.append(instruction)
    packet.extend(params)

    checksum = calc_checksum(packet)
    packet.append(checksum)

    return packet


def build_rx(packet_id=ID, error=ERROR, params=PARAMS):
    packet = [0xFF, 0xFF]
    packet.append(packet_id)
    packet.append(len(params) + 2)
    packet.append(error)
    packet.extend(params)

    checksum = calc_checksum(packet)
    packet.append(checksum)

    return packet


@pytest.fixture
def conn(mock_serial):
    with Connection(mock_serial.port, timeout=TIMEOUT) as conn:
        yield conn


def test_v1_read_packet(mock_serial, conn):
    rx = build_rx(error=0x01, params=[0xFF, 0xFF, 0xFD, 0xFD])
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = conn.read_packet()

    assert rx is not None

    assert rx.valid

    assert rx.error == 0x01

    assert rx.params.raw == bytes([0xFF, 0xFF, 0xFD, 0xFD])

    assert stub.called
    assert stub.calls == 1


def test_v1_read_packet_with_residue(mock_serial, conn):
    rx = build_rx(params=[0xFF, 0xFF, 0xFD, 0xFD])
    rx = [0x00] * 16 + rx
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = conn.read_packet()

    assert rx is not None

    assert rx.valid

    assert rx.error == ERROR

    assert rx.params.raw == bytes([0xFF, 0xFF, 0xFD, 0xFD])

    assert stub.called
    assert stub.calls == 1


def test_v1_read_packet_header_timeout(mock_serial, conn):
    rx = []
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = conn.read_packet()

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v1_read_packet_rest_timeout(mock_serial, conn):
    rx = build_rx()
    rx = rx[:3]
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = conn.read_packet()

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v1_read_packet_no_header(mock_serial, conn):
    rx = []
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = conn.read_packet()

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v1_read_packet_timeout(mock_serial, conn):
    rx = build_rx()
    rx[3] = 0xFF

    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = conn.read_packet()

    assert rx is None

    assert stub.called
    assert stub.calls == 1


@pytest.fixture
def bus(mock_serial):
    with MotorBus(mock_serial.port, timeout=TIMEOUT) as bus:
        yield bus


def test_v1_ping(mock_serial, bus):
    tx = build_tx(instruction=PING, params=[])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = bus.ping(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v1_read(mock_serial, bus):
    tx = build_tx(instruction=READ, params=[0x2B, 0x04])
    rx = build_rx(params=[0x20, 0x01, 0x02, 0x03])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = bus.read(ID, 0x2B, 4)

    assert r.ok
    assert r.data == 0x20010203

    assert stub.called
    assert stub.calls == 1


def test_v1_write(mock_serial, bus):
    tx = build_tx(instruction=WRITE, params=[0x08, 0x00, 0x02])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = bus.write(ID, 0x08, 2, 0x200)

    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v1_reg_write(mock_serial, bus):
    tx = build_tx(instruction=REG_WRITE, params=[0x1E, 0xF4, 0x01])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = bus.reg_write(ID, 0x1E, 2, 0x01F4)

    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v1_action(mock_serial, bus):
    tx = build_tx(BROADCAST_ID, ACTION, params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=b"x")

    bus.action()

    assert bus.conn.read() == b"x"

    assert stub.called
    assert stub.calls == 1


def test_v1_factory_reset(mock_serial, bus):
    tx = build_tx(instruction=FACTORY_RESET, params=[])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = bus.factory_reset(ID)

    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v1_reboot(mock_serial, bus):
    tx = build_tx(instruction=REBOOT, params=[])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = bus.reboot(ID)

    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v1_sync_write(mock_serial, bus):
    tx = build_tx(
        BROADCAST_ID,
        SYNC_WRITE,
        params=[0x1E, 0x04, ID, 0x10, 0x00, 0x50, 0x01, ID + 1, 0x20, 0x02, 0x60, 0x03],
    )
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    params = SyncParams(0x1E, 4)
    params.add_value(ID, 0x01500010)
    params.add_value(ID + 1, 0x03600220)

    r = bus.sync_write(params)

    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v1_bulk_read(mock_serial, bus):
    tx = build_tx(
        BROADCAST_ID, BULK_READ, params=[0x00, 0x02, ID, 0x1E, 0x04, ID + 1, 0x24]
    )
    rx_1 = build_rx(ID, params=[0x01, 0x82])
    rx_2 = build_rx(ID + 1, params=[0x01, 0x02, 0x03, 0x72])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx_1 + rx_2))

    params = BulkParams()
    params.add_address(ID, 0x1E, 2)
    params.add_address(ID + 1, 0x24, 4)

    r = bus.bulk_read(params)

    assert r.ok
    assert r.data == [0x0182, 0x01020372]

    assert stub.called
    assert stub.calls == 1
