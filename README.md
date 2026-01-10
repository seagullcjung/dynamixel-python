# Dynamixel Python

Dynamixel-Python is a simple library for communicating with Dynamixel motors. Both dynamixel protocol 1.0 and 2.0 is supported.

> [!WARNING]
> Currently this library is under active development and the public api is likely to change.

## Installation

This repo aims to support legacy python versions. Currently python 3.8+ is supported.

```bash
pip install dynamixel-python
```

## Quickstart

```python
from dxl2 import DynamixelSerialV2

port = DynamixelSerialV2("/dev/ttyUSB0")

# connect before use
port.connect()

info = port.ping(10)

# torque enable
port.write(dxl_id=10, address=64, length=1, value=1)

# move motors 1 and 2 to position 100
port.sync_write(dxl_ids=[1, 2], address=116, length=4, value=100)

# disconnect after use
port.disconnect()
```

All instructions are available as methods of `DynamixelSerialV2` or `DynamixelSerialV1` class.
