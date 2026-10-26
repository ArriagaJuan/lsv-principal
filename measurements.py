"""Procesamiento de mediciones y compensación temporal capturada parcialmente en video."""
from collections import deque
import math

class RollingAverage:
    def __init__(self, window=5):
        self.window = max(1, int(window))
        self.values = deque(maxlen=self.window)
        self.total = 0.0
        self.count = 0
        self.accumulated = 0.0

    def update(self, value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Valor no finito")
        self.values.append(value)
        self.count += 1
        self.total += value
        self.accumulated = self.total / self.count
        return sum(self.values) / len(self.values)


def convert_velocity(value, unit="m/min"):
    """Devuelve velocidad en m/min desde unidades explícitas, sin heurísticas riesgosas."""
    value = float(value)
    if unit == "m/min":
        return value
    if unit == "km/h":
        return value * 1000.0 / 60.0
    if unit == "m/s":
        return value * 60.0
    raise ValueError(f"Unidad desconocida: {unit}")


def integrate_distance(previous_time, previous_speed, current_time, current_speed, total=0.0):
    """Integral trapezoidal de velocidad m/min en tiempo s → distancia m."""
    dt = max(0.0, float(current_time) - float(previous_time))
    return float(total) + dt * (float(previous_speed) + float(current_speed)) / 120.0


def mask_reset_transients(times, values, display_times=None, cutoff_seconds=2.0):
    """Corrección aproximada para picos tras un reset (requiere validar con datos reales)."""
    if len(times) != len(values) or not values:
        raise ValueError("Las series deben tener igual longitud y no estar vacías")
    display_times = list(display_times) if display_times is not None else list(times)
    if len(display_times) != len(times):
        raise ValueError("Tiempos de visualización incompatibles")
    if len(times) < 2:
        return list(values)
    first_t, first_v = float(times[0]), float(values[0])
    second_t, second_v = float(times[1]), float(values[1])
    if second_t <= first_t:
        return list(values)
    acceleration = (second_v - first_v) / (second_t - first_t)
    corrected = []
    for t, raw in zip(display_times, values):
        t = float(t)
        if t <= float(cutoff_seconds):
            corrected.append(first_v + acceleration * max(0.0, t))
        else:
            corrected.append(float(raw))
    return corrected


def continuity_report(times, expected_period, gap_factor=3.0):
    """Distingue falta de muestras y períodos anormales de adquisición."""
    expected_period = float(expected_period)
    if expected_period <= 0:
        raise ValueError("Período esperado inválido")
    gaps = []
    for i in range(1, len(times)):
        delta = float(times[i]) - float(times[i - 1])
        if delta <= 0 or delta > expected_period * float(gap_factor):
            gaps.append({"index": i, "delta_s": delta})
    return {"sample_count": len(times), "gaps": gaps, "gap_count": len(gaps)}
