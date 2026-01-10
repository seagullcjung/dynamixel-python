import pytest
from serial import Serial

from dxl2.protocol_v2 import (
    DynamixelSerialV2,
    HardwareError,
    InstructionPacketV2,
    calc_crc_16,
    receive,
    split_bytes,
    transmit,
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
CLEAR = 0x10
CONTROL_TABLE_BACKUP = 0x20
SYNC_READ = 0x82
SYNC_WRITE = 0x83
FAST_SYNC_READ = 0x8A
BULK_READ = 0x92
BULK_WRITE = 0x93
FAST_BULK_READ = 0x9A


def build_tx(packet_id=ID, instruction=INST, params=PARAMS):
    packet = [0xFF, 0xFF, 0xFD, 0x00]
    packet.append(packet_id)
    packet.extend(split_bytes(len(params) + 3))
    packet.append(instruction)
    packet.extend(params)

    crc = calc_crc_16(packet)
    packet.extend(split_bytes(crc))

    return packet


def build_rx(packet_id=ID, error=ERROR, params=PARAMS):
    packet = [0xFF, 0xFF, 0xFD, 0x00]
    packet.append(packet_id)
    packet.extend(split_bytes(len(params) + 4))
    packet.append(0x55)
    packet.append(error)
    packet.extend(params)

    crc = calc_crc_16(packet)
    packet.extend(split_bytes(crc))

    return packet


def test_v2_transmit(mock_serial):
    tx = build_tx(params=[0xFF, 0xFF, 0xFD, 0xFD])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=b"x")

    serial = Serial(mock_serial.port, timeout=TIMEOUT)

    tx = InstructionPacketV2(ID, INST, [0xFF, 0xFF, 0xFD])
    transmit(serial, tx)

    assert serial.read() == b"x"

    assert stub.called
    assert stub.calls == 1


def test_v2_transmit_raises(mocker, mock_serial):
    serial = Serial(mock_serial.port, timeout=TIMEOUT)

    mocker.patch.object(serial, "write", return_value=1)

    tx = InstructionPacketV2(0, 0)

    with pytest.raises(ConnectionError):
        transmit(serial, tx)


def test_v2_receive(mock_serial):
    rx = build_rx(error=0x12, params=[0xFF, 0xFF, 0xFD, 0xFD])
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = receive(serial)

    assert rx is not None

    assert rx.valid

    assert rx.error == 0x12
    assert rx.instruction == 0x55

    assert rx.params == [0xFF, 0xFF, 0xFD]

    assert stub.called
    assert stub.calls == 1


def test_v2_receive_with_residue(mock_serial):
    rx = build_rx(params=[0xFF, 0xFF, 0xFD, 0xFD])
    rx = [0x00] * 16 + rx
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = receive(serial)

    assert rx is not None

    assert rx.valid

    assert rx.error == ERROR
    assert rx.instruction == 0x55

    assert rx.params == [0xFF, 0xFF, 0xFD]

    assert stub.called
    assert stub.calls == 1


def test_v2_receive_header_timeout(mock_serial):
    rx = []
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = receive(serial)

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v2_receive_rest_timeout(mock_serial):
    rx = build_rx()
    rx = rx[:5]
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = receive(serial)

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v2_rx_receive_no_header(mock_serial):
    rx = [0x00] * 16
    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = receive(serial)

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v2_receive_timeout(mock_serial):
    rx = build_rx()
    rx[6] = 0xFF

    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    rx = receive(serial)

    assert rx is None

    assert stub.called
    assert stub.calls == 1


def test_v2_receive_raises(mock_serial):
    rx = build_rx(error=0x82)

    stub = mock_serial.stub(receive_bytes=b"x", send_bytes=bytes(rx))

    serial = Serial(mock_serial.port, timeout=TIMEOUT)
    serial.write(b"x")

    with pytest.raises(HardwareError):
        receive(serial)

    assert stub.called
    assert stub.calls == 1


@pytest.fixture
def port(mock_serial):
    port = DynamixelSerialV2(mock_serial.port, timeout=TIMEOUT)

    port.connect()
    yield port
    port.disconnect()


def test_v2_ping(mock_serial, port):
    tx = build_tx(instruction=PING, params=[])
    rx = build_rx(params=[0x06, 0x04, 0x26])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.ping(ID)

    assert r.ok
    assert r.data == {ID: {"model_number": 1030, "firmware_version": 38}}

    assert stub.called
    assert stub.calls == 1


def test_v2_broadcast_ping(mock_serial, port):
    tx = build_tx(BROADCAST_ID, PING, params=[])

    rx_1 = build_rx(packet_id=0x01, params=[0x06, 0x04, 0x26])
    rx_2 = build_rx(packet_id=0x02, params=[0x05, 0x04, 0x25])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx_1 + rx_2))

    r = port.broadcast_ping()

    assert r.ok
    assert r.data == {
        1: {"model_number": 1030, "firmware_version": 38},
        2: {"model_number": 1029, "firmware_version": 37},
    }

    assert stub.called
    assert stub.calls == 1


def test_v2_read(mock_serial, port):
    tx = build_tx(instruction=READ, params=[0x84, 0x01, 0x04, 0x00])
    rx = build_rx(params=[0xA6, 0x01, 0x01, 0x01])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.read(ID, 0x0184, 4)

    assert r.ok
    assert r.data == 0x010101A6

    assert stub.called
    assert stub.calls == 1


def test_v2_write(mock_serial, port):
    tx = build_tx(instruction=WRITE, params=[0x74, 0x01, 0x04, 0x01, 0x01, 0x01])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.write(ID, 0x0174, 4, 0x01010104)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_reg_write(mock_serial, port):
    tx = build_tx(instruction=REG_WRITE, params=[0x68, 0x01, 0xC8, 0x00, 0x00, 0x01])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.reg_write(ID, 0x0168, 4, 0x010000C8)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_action(mock_serial, port):
    tx = build_tx(instruction=ACTION, params=[])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.action(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_factory_reset(mock_serial, port):
    tx = build_tx(instruction=FACTORY_RESET, params=[0xFF])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.factory_reset(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_factory_reset_except_id(mock_serial, port):
    tx = build_tx(instruction=FACTORY_RESET, params=[0x01])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.factory_reset_except_id(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_factory_reset_except_id_baudrate(mock_serial, port):
    tx = build_tx(instruction=FACTORY_RESET, params=[0x02])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.factory_reset_except_id_baudrate(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_reboot(mock_serial, port):
    tx = build_tx(instruction=REBOOT, params=[])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.reboot(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_clear_position(mock_serial, port):
    tx = build_tx(instruction=CLEAR, params=[0x01, 0x44, 0x58, 0x4C, 0x22])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.clear_position(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_clear_errors(mock_serial, port):
    tx = build_tx(instruction=CLEAR, params=[0x02, 0x45, 0x52, 0x43, 0x4C])
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.clear_errors(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_control_table_backup(mock_serial, port):
    tx = build_tx(
        instruction=CONTROL_TABLE_BACKUP, params=[0x01, 0x43, 0x54, 0x52, 0x4C]
    )
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.control_table_backup(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_control_table_restore(mock_serial, port):
    tx = build_tx(
        instruction=CONTROL_TABLE_BACKUP, params=[0x02, 0x43, 0x54, 0x52, 0x4C]
    )
    rx = build_rx(params=[])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.control_table_restore(ID)
    assert r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_sync_read(mock_serial, port):
    tx = build_tx(BROADCAST_ID, SYNC_READ, params=[0x84, 0x01, 0x04, 0x00, 0x01, 0x02])

    rx_1 = build_rx(params=[0xA6, 0x01, 0x01, 0x01])
    rx_2 = build_rx(ID + 1, params=[0xB6, 0x01, 0x01, 0x01])

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx_1 + rx_2))

    r = port.sync_read([ID, ID + 1], 0x0184, 4)

    assert r.ok
    assert r.data == [0x010101A6, 0x010101B6]

    assert stub.called
    assert stub.calls == 1


def test_v2_sync_read_partial(mock_serial, port):
    tx = build_tx(BROADCAST_ID, SYNC_READ, params=[0x84, 0x01, 0x04, 0x00, 0x01, 0x02])

    rx_1 = build_rx(params=[0xA6, 0x01, 0x01, 0x01])
    rx_2 = []

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx_1 + rx_2))

    r = port.sync_read([ID, ID + 1], 0x0184, 4)

    assert not r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_sync_write(mock_serial, port):
    params = [0x74, 0x01]
    params.extend([0x04, 0x00])

    params.append(0x01)
    params.extend(split_bytes(0x01010196, n_bytes=4))

    params.append(0x02)
    params.extend(split_bytes(0x01210136, n_bytes=4))

    tx = build_tx(BROADCAST_ID, SYNC_WRITE, params)

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=b"x")

    port.sync_write([1, 2], 0x0174, 4, [0x01010196, 0x01210136])

    assert port.serial.read() == b"x"

    assert stub.called
    assert stub.calls == 1


def test_v2_fast_sync_read(mock_serial, port):
    params = [0x84, 0x01]
    params.extend([0x04, 0x00])
    params.extend([0x01, 0x02, 0x03])

    tx = build_tx(BROADCAST_ID, FAST_SYNC_READ, params)

    params = [0x01]
    params.extend(split_bytes(0x28937423, n_bytes=4))
    params.extend([0x00, 0x00])

    params.append(0x00)
    params.append(0x02)
    params.extend(split_bytes(0x27933423, n_bytes=4))
    params.extend([0x00, 0x00])

    params.append(0x00)
    params.append(0x03)
    params.extend(split_bytes(0x17933423, n_bytes=4))

    rx = build_rx(BROADCAST_ID, params=params)

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.fast_sync_read([1, 2, 3], 0x0184, 4)

    assert r.ok
    assert r.data == [0x28937423, 0x27933423, 0x17933423]

    assert stub.called
    assert stub.calls == 1


def test_v2_fast_sync_read_single(mock_serial, port):
    params = [0x84, 0x01]
    params.extend([0x04, 0x00])
    params.extend([0x01])

    tx = build_tx(BROADCAST_ID, FAST_SYNC_READ, params)

    params = [0x01]
    params.extend(split_bytes(0x28937423, n_bytes=4))

    rx = build_rx(BROADCAST_ID, params=params)

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.fast_sync_read([1], 0x0184, 4)

    assert r.ok
    assert r.data == [0x28937423]

    assert stub.called
    assert stub.calls == 1


def test_v2_bulk_read(mock_serial, port):
    params = []

    params.append(0x01)
    params.extend(split_bytes(0x0124))
    params.extend(split_bytes(0x004))

    params.append(0x02)
    params.extend(split_bytes(0x0114))
    params.extend(split_bytes(0x002))

    params.append(0x03)
    params.extend(split_bytes(0x0110))
    params.extend(split_bytes(0x001))

    tx = build_tx(BROADCAST_ID, BULK_READ, params)

    rx_1 = build_rx(0x01, params=split_bytes(0x34832902, n_bytes=4))
    rx_2 = build_rx(0x02, params=split_bytes(0x8329, n_bytes=2))
    rx_3 = build_rx(0x03, params=split_bytes(0x39, n_bytes=1))

    stub = mock_serial.stub(
        receive_bytes=bytes(tx), send_bytes=bytes(rx_1 + rx_2 + rx_3)
    )

    r = port.bulk_read([1, 2, 3], [0x0124, 0x0114, 0x0110], [4, 2, 1])

    assert r.ok
    assert r.data == [0x34832902, 0x8329, 0x39]

    assert stub.called
    assert stub.calls == 1


def test_v2_bulk_read_partial(mock_serial, port):
    params = []

    params.append(0x01)
    params.extend(split_bytes(0x0124))
    params.extend(split_bytes(0x004))

    params.append(0x02)
    params.extend(split_bytes(0x0114))
    params.extend(split_bytes(0x002))

    params.append(0x03)
    params.extend(split_bytes(0x0110))
    params.extend(split_bytes(0x001))

    tx = build_tx(BROADCAST_ID, BULK_READ, params)

    rx_1 = build_rx(0x01, params=split_bytes(0x34832902, n_bytes=4))
    rx_2 = build_rx(0x02, params=split_bytes(0x8329, n_bytes=2))
    rx_3 = []

    stub = mock_serial.stub(
        receive_bytes=bytes(tx), send_bytes=bytes(rx_1 + rx_2 + rx_3)
    )

    r = port.bulk_read([1, 2, 3], [0x0124, 0x0114, 0x0110], [4, 2, 1])

    assert not r.ok

    assert stub.called
    assert stub.calls == 1


def test_v2_bulk_write(mock_serial, port):
    params = []

    params.append(0x01)
    params.extend(split_bytes(0x0124))
    params.extend(split_bytes(0x004))
    params.extend(split_bytes(0x34832902, n_bytes=4))

    params.append(0x02)
    params.extend(split_bytes(0x0114))
    params.extend(split_bytes(0x002))
    params.extend(split_bytes(0x8329, n_bytes=2))

    params.append(0x03)
    params.extend(split_bytes(0x0110))
    params.extend(split_bytes(0x001))
    params.extend(split_bytes(0x39, n_bytes=1))

    tx = build_tx(BROADCAST_ID, BULK_WRITE, params)

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=b"x")

    port.bulk_write(
        [1, 2, 3], [0x0124, 0x0114, 0x0110], [4, 2, 1], [0x34832902, 0x8329, 0x39]
    )

    assert port.serial.read() == b"x"

    assert stub.called
    assert stub.calls == 1


def test_v2_fast_bulk_read(mock_serial, port):
    params = []

    params.append(0x01)
    params.extend(split_bytes(0x0124))
    params.extend(split_bytes(0x004))

    params.append(0x02)
    params.extend(split_bytes(0x0114))
    params.extend(split_bytes(0x002))

    params.append(0x03)
    params.extend(split_bytes(0x0110))
    params.extend(split_bytes(0x001))

    tx = build_tx(BROADCAST_ID, FAST_BULK_READ, params)

    params = [0x01]
    params.extend(split_bytes(0x28937423, n_bytes=4))
    params.extend([0x00, 0x00])

    params.append(0x00)
    params.append(0x02)
    params.extend(split_bytes(0x2933, n_bytes=2))
    params.extend([0x00, 0x00])

    params.append(0x00)
    params.append(0x03)
    params.extend(split_bytes(0x13, n_bytes=1))

    rx = build_rx(BROADCAST_ID, params=params)

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.fast_bulk_read([1, 2, 3], [0x0124, 0x0114, 0x0110], [4, 2, 1])

    assert r.ok
    assert r.data == [0x28937423, 0x2933, 0x13]

    assert stub.called
    assert stub.calls == 1


def test_v2_fast_bulk_read_single(mock_serial, port):
    params = []

    params.append(0x01)
    params.extend(split_bytes(0x0124))
    params.extend(split_bytes(0x004))

    tx = build_tx(BROADCAST_ID, FAST_BULK_READ, params)

    params = [0x01]
    params.extend(split_bytes(0x28937423, n_bytes=4))

    rx = build_rx(BROADCAST_ID, params=params)

    stub = mock_serial.stub(receive_bytes=bytes(tx), send_bytes=bytes(rx))

    r = port.fast_bulk_read([1], [0x0124], [4])

    assert r.ok
    assert r.data == [0x28937423]

    assert stub.called
    assert stub.calls == 1
