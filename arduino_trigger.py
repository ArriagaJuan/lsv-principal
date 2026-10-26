"""Compatibilidad de nombre del módulo mostrado en el video LSV principal.

Usa el firmware TTL V1 original confirmado por el usuario; NO las variantes
Kistler V2/V3 del video. Mantiene una sola implementación de protocolo.
"""
from trigger import TriggerController, MAX_DURATION_US

ArduinoTrigger = TriggerController

__all__ = ["ArduinoTrigger", "TriggerController", "MAX_DURATION_US"]
