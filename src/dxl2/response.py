from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
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
