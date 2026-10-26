"""Ciclos, intentos y pausas del plan de adquisición (recuperación guiada por video)."""
from dataclasses import dataclass
import time

@dataclass(frozen=True)
class Attempt:
    cycle: int
    attempt: int
    status: str
    reason: str
    planned_seconds: float
    elapsed_seconds: float

class AcquisitionPlan:
    def __init__(self, duration_seconds, total_cycles, pause_seconds=0.0, now=None):
        self.duration_seconds = float(duration_seconds)
        self.total_cycles = int(total_cycles)
        self.pause_seconds = float(pause_seconds)
        if self.duration_seconds <= 0 or self.total_cycles < 1 or self.pause_seconds < 0:
            raise ValueError("Duración/ciclos/pausa inválidos")
        self._now = now or time.monotonic
        self.completed_cycles = 0
        self.current_cycle = 1
        self.current_attempt = 0
        self.attempts = []
        self.state = "idle"
        self._attempt_started = None

    @property
    def active(self):
        return self.state == "running" and self._attempt_started is not None

    def start_attempt(self):
        if self.active:
            raise RuntimeError("Ya existe un intento activo.")
        if self.current_cycle > self.total_cycles:
            raise RuntimeError("El plan ya terminó.")
        self.current_attempt += 1
        self._attempt_started = self._now()
        self.state = "running"

    def _close_attempt(self, status, reason=""):
        if not self.active:
            return None
        elapsed = max(0.0, self._now() - self._attempt_started)
        result = Attempt(self.current_cycle, self.current_attempt, status, reason,
                         self.duration_seconds, elapsed)
        self.attempts.append(result)
        self._attempt_started = None
        return result

    def interrupt(self, reason):
        result = self._close_attempt("Interrumpido", str(reason))
        if result:
            self.state = "paused"
        return result

    def fail(self, reason):
        result = self._close_attempt("Error", str(reason))
        if result:
            self.state = "paused"
        return result

    def complete_attempt(self):
        result = self._close_attempt("Completo")
        if result is None:
            return None
        self.completed_cycles += 1
        self.current_cycle += 1
        self.current_attempt = 0
        self.state = "completed" if self.completed_cycles >= self.total_cycles else "waiting"
        return result

    def add_cycles(self, count=1):
        count = int(count)
        if count < 1:
            raise ValueError("La cantidad de ciclos debe ser positiva")
        self.total_cycles += count
        if self.state == "completed":
            self.state = "waiting"
        return self.total_cycles

    def current_remaining(self):
        if not self.active:
            return self.duration_seconds if self.state == "paused" else 0.0
        return max(0.0, self.duration_seconds - (self._now() - self._attempt_started))

    def plan_remaining(self):
        if self.completed_cycles >= self.total_cycles:
            return 0.0
        pending_after_current = max(0, self.total_cycles - self.current_cycle)
        current = self.current_remaining() if self.active else self.duration_seconds
        pauses = pending_after_current + (1 if self.state == "waiting" else 0)
        return current + pending_after_current * self.duration_seconds + pauses * self.pause_seconds
