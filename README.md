# Dynamixel Python

![test workflow](https://github.com/seagullcjung/dynamixel-python/actions/workflows/test.yaml/badge.svg)

Dynamixel-Python is a user-friendly library for communicating with Dynamixel motors. Both dynamixel protocol 1.0 and 2.0 is supported.

## Installation

This repo aims to support legacy python versions. Currently python 3.8+ is supported.

```bash
pip install dynamixel-python
```

## Features

### Scanning for motors

Scan for motors connected to your controller. You need to set the baudrate of the motor to be able to communicate with it. The default baudrate is 1M.

```python
from dxl2.v2 import MotorBus


bus = MotorBus(port="/dev/ttyUSB0")

# connect before use
bus.connect()

motors = bus.scan()
print(motors)

# disconnect after use
bus.disconnect()
```

### Ping motor

You can ping your motors to see if it is connected. Provide the ID of the motor to `bus.ping` to get a response. The response contains a property ok which checks for read timeout, data corruption. If all is okay, you can access the data property to get the parsed data.

```python
from dxl2.v2 import MotorBus


bus = MotorBus(port="/dev/ttyUSB0", baudrate=1_000_000)

bus.connect()

r = bus.ping(dxl_id=0)

# print data if response is okay
if r.ok:
    print(r.data)

bus.disconnect()
```

### Broadcast Ping

You can send a broadcast ping to get responses from all motors connected to your controller. Note that read timeouts can't be detected since read timeout is used to detect the end. Therefore, it is not a reliable method to search for motors.

```python
r = bus.broadcast_ping()

if r.ok:
    print(r.data)
```

### Read

You can read data from the control table of a specific motor indexed by their ID using the `bus.read` method. The below example shows reading the present position of the motor. If your data is signed, you can set `signed=True` to get negative values.

```python
r = bus.read(dxl_id=0, address=132, length=4, signed=False)

if r.ok:
    print(r.data)
```

### Write

You can write to the control table of a specific motor indexed by their ID using the `bus.write` method. The below example shows writing the goal position of the motor. If the data you're writing is signed, set `signed=False`.

```python
r = bus.write(dxl_id=0, address=116, length=4, value=0, signed=False)

assert r.ok
```

### Sync Read

Using multiple write commands can result in timing differences between motors. Sync read provides a method to read from specified motors synchronously. Note that you can only read from the same location in the control table. 

For the sync commands, you need to build the parameter using the `SyncParams` class. First specify where to read from and if it's signed. Then add motors to the params with the `params.add_motor` method.

```python
from dxl2.v2 import SyncParams


params = SyncParams(address=132, length=4, signed=False)
params.add_motor(dxl_id=0)
params.add_motor(dxl_id=1)
params.add_motor(dxl_id=2)

r = bus.sync_read(params=params)

if r.ok:
    print(r.data)
```

### Sync Write

Similarly, you can write synchronously to multiple motors by using the `bus.sync_write` method.

```python
from dxl2.v2 import SyncParams

params = SyncParams(address=132, length=4, signed=False)
params.add_value(dxl_id=0, value=100)
params.add_value(dxl_id=1, value=200)
params.add_value(dxl_id=2, value=300)

r = bus.sync_write(params=params)

assert r.ok
```

### Fast Sync Read

Fast sync read read allows faster reads by returning a single packet where as sync read returns multiple packets. This is only supported for X430/540 series (firmware v45 or above, 2XL/2XC not supported), X330 (firmware v46 or above), P series (firmware v12 or above), and RH-P12-RN(A) (firmware v13 or above).

The usage is the same as `bus.sync_read`.

```python
from dxl2.v2 import SyncParams


params = SyncParams(address=116, length=4, signed=False)
params.add_motor(dxl_id=0)
params.add_motor(dxl_id=1)
params.add_motor(dxl_id=2)

r = bus.sync_read(params=params, signed=False)

if r.ok:
    print(r.data)
```

### Bulk Read

Bulk commands allow you to read or write to different locations. However, you cannot read or write to the same motor multiple times. Similar to sync commands, you first build the parameter using the `BulkParams` class but this time you do not supply the address, length, and signed information at init since bulk commands can read or write to different locations. Use the `params.add_address` method to add where to read from and if it is signed.

```python
from dxl2.v2 import BulkParams


params = BulkParams()
params.add_address(dxl_id=0, address=132, length=4, signed=False)
params.add_address(dxl_id=1, address=120, length=2, signed=False)
params.add_address(dxl_id=2, address=122, length=1, signed=False)

r = bus.bulk_read(params)

assert r.ok
```

### Bulk Write

Bulk write allows you to write to different locations with differing lengths of data. The usage is similar to bulk read. Add values you want to write with the `params.add_value` method.

```python
from dxl2.v2 import BulkParams


params = BulkParams()
params.add_value(dxl_id=0, address=32, length=2, value=160, signed=False)
params.add_value(dxl_id=1, address=31, length=1, value=80, signed=False)

r = bus.bulk_read(params)

assert r.ok
```

### Fast Bulk Read

Similar to fast sync read, fast bulk read allows you to read data faster. The usage is the same as bulk read.

```python
from dxl2.v2 import BulkParams


params = BulkParams()
params.add_address(dxl_id=3, address=132, length=4, signed=False)
params.add_address(dxl_id=7, address=124, length=2, signed=False)
params.add_address(dxl_id=4, address=146, length=1, signed=False)

r = bus.bulk_read(params)

assert r.ok
```

### Register Write

Register write delays the write until an action command is received. The usage is same as the write command.

```python
r = bus.reg_write(dxl_id=0, address=116, length=4, value=0, signed=False)

assert r.ok
```
### Action

The action command allows the write operation from the register write command to be executed.

```python
r = bus.reg_write(dxl_id=0)

assert r.ok
```
### Factory Reset

You can reset the motor including the ID and baudrate with this command. When the broadcast When the broadcast ID 0xFE is used this command will not be executed.

```python
r = bus.factory_reset(dxl_id=0)

assert r.ok
```

### Factory Reset except ID

You can reset the motor execpt the ID using this command.

```python
r = bus.factory_reset_except_id(dxl_id=0)

assert r.ok
```

### Factory Reset except ID and Baudrate

You can reset the motor execpt the ID and baudrate using this command.

```python
r = bus.factory_reset_except_id_baudrate(dxl_id=0)

assert r.ok
```

### Reboot

You can reboot the motor using this command:

```python
r = bus.reboot(dxl_id=0)

assert r.ok
```

### Clear Position

You can reset the present position value to an absolute value within one rotation (0-4095) when the motor is stopped. When the motor is moving, the response will not be okay.

```python
r = bus.clear_position(dxl_id=0)

assert r.ok
```

### Clear Errors

You can try to clear any registered error that have occurred. If the error cannot be cleared, the response will not be okay.

```python
r = bus.clear_errors(dxl_id=0)

assert r.ok
```

### Control Table Backup

You can backup the control table when torque is not enabled. If it is, the response will not be okay. This is supported for X430/540 series (firmware v45 or above), X330 series (firmware v46 or above), P series (firmware v12 or above).

```python
r = bus.control_table_backup(dxl_id=0)

assert r.ok
```

### Control Table Restore

When the control table is backed up, you can restore the control table with this command. The motor will reboot after restoring.

```python
r = bus.control_table_restore(dxl_id=0)

assert r.ok
```
