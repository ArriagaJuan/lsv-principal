"""Cálculos auxiliares offline para verificación contra instrumentos patrón.

Estos cálculos NO son una transcripción literal de calculos.py en la grabación.
Todas las unidades son explícitas. No se aplica corrección automática.
"""
from statistics import fmean, stdev
from measurements import RollingAverage, convert_velocity, integrate_distance, continuity_report


def hz_a_velocidad_kmh(frecuencia_hz, diametro_m, marcas_por_vuelta):
    """Rueda: frecuencia de eventos -> velocidad km/h."""
    from math import pi, isfinite
    f, d = float(frecuencia_hz), float(diametro_m)
    marks = int(marcas_por_vuelta)
    if not all(map(isfinite, (f, d))) or f < 0 or d <= 0 or marks <= 0:
        raise ValueError('Frecuencia, diámetro o marcas por vuelta inválidos')
    return f * pi * d * 3.6 / marks


def resumen_velocidad_m_min(datos):
    """Estadística descriptiva; no se calcula incertidumbre metrológica."""
    values = [float(x) for x in datos]
    if not values:
        raise ValueError('No hay valores')
    return {'n':len(values),'media_m_min':fmean(values),
            'desv_est_m_min':stdev(values) if len(values)>1 else 0.0,
            'min_m_min':min(values),'max_m_min':max(values)}
