from enum import Enum


class ProbeType(str, Enum):
    LIVENESS = "liveness"
    READINESS = "readiness"

    def __str__(self) -> str:
        return str(self.value)
