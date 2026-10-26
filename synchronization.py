"""Alineación de reloj del láser respecto del origen de referencia."""
import math


def estimate_time_offset(lsv_distances, ref_distances, speed_m_min, max_offset_seconds=2.0):
    """Aproxima desfase temporal desde una diferencia de distancia.

    No reemplaza una calibración de trigger. Firmas y aproximación procedentes
    de los fotogramas; signo del desfase requiere validación experimental.
    """
    if not lsv_distances or not ref_distances or not speed_m_min:
        return 0.0
    n = min(len(lsv_distances), len(ref_distances))
    if n < 1:
        return 0.0
    diff = [float(ref_distances[i]) - float(lsv_distances[i]) for i in range(n)]
    offset = (sum(diff) / n) * 60.0 / float(speed_m_min)
    return max(-max_offset_seconds, min(max_offset_seconds, offset)) if math.isfinite(offset) else 0.0


def align_r3(time_r, offset_s):
    """Fotograma observado: R3 = floor((time_r + offset_s) * 1000)/1000."""
    return math.floor((float(time_r) + float(offset_s)) * 1000.0) / 1000.0
