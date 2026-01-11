from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class Response:
    timeout: bool = False
    error: Optional[int] = None
    valid: Optional[bool] = None
    data: Optional[Any] = None

    @classmethod
    def from_rx(cls, rx):
        if rx is None:
            return cls(timeout=True)

        if rx.valid and rx.error == 0:
            data = rx.params
        else:
            data = rx.params.raw

        return cls(error=rx.error, valid=rx.valid, data=data)

    @property
    def ok(self):
        return not self.timeout and self.error == 0 and self.valid
