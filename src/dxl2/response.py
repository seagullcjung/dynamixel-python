from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Response:
    timeout: bool = False
    error: Optional[int] = None
    valid: Optional[bool] = None
    data: Optional[Any] = None

    @property
    def ok(self) -> bool:
        if self.error is None or self.valid is None:
            return False

        return not self.timeout and self.error == 0 and self.valid
