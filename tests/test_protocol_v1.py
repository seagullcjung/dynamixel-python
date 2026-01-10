import pytest
from serial import Serial

from dxl2.protocol_v1 import (
    DynamixelSerialV1,
    InstructionPacketV1,
    StatusPacketV1,
    calc_checksum,
)

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


def test_tx_v1_write_to(mock_serial):
    tx = build_tx()

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=b"x")

    serial = Serial(mock_serial.port, timeout=TIMEOUT)

    tx = InstructionPacketV1(ID, INST, PARAMS)
    ok = tx.write_to(serial)
    assert ok

    assert serial.read() == b"x"

    assert stub.called
    assert stub.calls == 1


def test_v1_tx_write_to_timeout(mocker, mock_serial):
    serial = Serial(mock_serial.port, timeout=TIMEOUT)

    mocker.patch.object(serial, "write", return_value=1)

    tx = InstructionPacketV1(0, 0)
    ok = tx.write_to(serial)
    assert not ok


def test_v1_rx_read_from(mock_serial):
    rx = build_rx(error=0x01, params=[0xFF, 0xFF, 0xFD, 0xFD])
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = StatusPacketV1.read_from(serial)

    assert rx is not None

    assert rx.is_valid()

    assert rx.error == 0x01

    assert rx.params == [0xFF, 0xFF, 0xFD, 0xFD]

    assert stub.called
    assert stub.calls == 1


def test_v1_rx_read_from_residue(mock_serial):
    rx = build_rx(params=[0xFF, 0xFF, 0xFD, 0xFD])
    rx = [0x00] * 16 + rx
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = StatusPacketV1.read_from(serial)

    assert rx is not None

    assert rx.is_valid()

    assert rx.error == ERROR

    assert rx.params == [0xFF, 0xFF, 0xFD, 0xFD]

    assert stub.called
    assert stub.calls == 1


def test_v1_read_from_header_timeout(mock_serial):
    rx = []
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = StatusPacketV1.read_from(serial)

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v1_read_from_rest_timeout(mock_serial):
    rx = build_rx()
    rx = rx[:3]
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = StatusPacketV1.read_from(serial)

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v1_rx_read_from_no_header(mock_serial):
    rx = []
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = StatusPacketV1.read_from(serial)

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v1_rx_read_from_timeout(mock_serial):
    rx = build_rx()
    rx[3] = 0xFF

    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = StatusPacketV1.read_from(serial)

    assert rx is None

    assert stub.called
    assert stub.calls == 1


@pytest.fixture
def port(mock_serial):
    port = DynamixelSerialV1(mock_serial.port, timeout=TIMEOUT)

    port.connect()
    yield port
    port.disconnect()


def test_v1_ping(mock_serial, port):
    tx = build_tx(instruction=PING, params=[])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    ok = port.ping(ID)
    assert ok

    assert stub.called
    assert stub.calls == 1


def test_v1_read(mock_serial, port):
    tx = build_tx(instruction=READ, params=[0x2B, 0x04])
    rx = build_rx(params=[0x20, 0x01, 0x02, 0x03])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    data = port.read(ID, 0x2B, 4)

    assert data == 0x20010203

    assert stub.called
    assert stub.calls == 1


def test_v1_write(mock_serial, port):
    tx = build_tx(instruction=WRITE, params=[0x08, 0x00, 0x02])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    ok = port.write(ID, 0x08, 2, 0x200)

    assert ok

    assert stub.called
    assert stub.calls == 1


def test_v1_reg_write(mock_serial, port):
    tx = build_tx(instruction=REG_WRITE, params=[0x1E, 0xF4, 0x01])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    ok = port.reg_write(ID, 0x1E, 2, 0x01F4)

    assert ok

    assert stub.called
    assert stub.calls == 1


def test_v1_action(mock_serial, port):
    tx = build_tx(BROADCAST_ID, ACTION, params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=b"x")

    ok = port.action()

    assert ok

    assert port.serial.read() == b"x"

    assert stub.called
    assert stub.calls == 1


def test_v1_factory_reset(mock_serial, port):
    tx = build_tx(instruction=FACTORY_RESET, params=[])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    ok = port.factory_reset(ID)

    assert ok

    assert stub.called
    assert stub.calls == 1


def test_v1_reboot(mock_serial, port):
    tx = build_tx(instruction=REBOOT, params=[])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    ok = port.reboot(ID)

    assert ok

    assert stub.called
    assert stub.calls == 1


def test_v1_sync_write(mock_serial, port):
    tx = build_tx(
        BROADCAST_ID,
        SYNC_WRITE,
        params=[0x1E, 0x04, ID, 0x10, 0x00, 0x50, 0x01, ID + 1, 0x20, 0x02, 0x60, 0x03],
    )

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=b"x")

    ok = port.sync_write([ID, ID + 1], 0x1E, 4, [0x01500010, 0x03600220])
    assert ok

    assert port.serial.read() == b"x"

    assert stub.called
    assert stub.calls == 1


def test_v1_bulk_read(mock_serial, port):
    tx = build_tx(
        BROADCAST_ID, BULK_READ, params=[0x00, 0x02, ID, 0x1E, 0x04, ID + 1, 0x24]
    )
    rx_1 = build_rx(ID, params=[0x01, 0x82])
    rx_2 = build_rx(ID + 1, params=[0x01, 0x02, 0x03, 0x72])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx_1 + rx_2))

    data = port.bulk_read([ID, ID + 1], [0x1E, 0x24], [2, 4])

    assert data == [0x0182, 0x01020372]

    assert stub.called
    assert stub.calls == 1
