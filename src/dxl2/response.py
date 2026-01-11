from dataclasses import dataclass
from typing import Any, Optional


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
