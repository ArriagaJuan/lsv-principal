"""Diagnóstico NO ACTUANTE del generador Agilent/Keysight 33220A.

La grabación identifica su controlador VISA, pero no confirma todos los comandos
ni la topología GPIB. Únicamente expone identificación estándar *IDN?.
No habilita ni modifica la salida del generador.
"""
class Agilent33220A:
    def __init__(self, resource_name, resource_manager=None):
        self.resource_name = str(resource_name)
        self._rm = resource_manager
        self.instrument = None
        self._owns_rm = resource_manager is None

    def connect_readonly(self):
        if self.instrument is not None:
            return self.identify()
        if self._rm is None:
            import pyvisa  # instalacion opcional: pip install pyvisa
            self._rm = pyvisa.ResourceManager()
        self.instrument = self._rm.open_resource(self.resource_name)
        self.instrument.timeout = 2000
        try:
            return self.identify()
        except Exception:
            self.close()
            raise

    def identify(self):
        if self.instrument is None:
            raise RuntimeError('Primero conecta el generador')
        return str(self.instrument.query('*IDN?')).strip()

    def close(self):
        if self.instrument is not None:
            self.instrument.close()
            self.instrument = None
        if self._owns_rm and self._rm is not None:
            self._rm.close()
            self._rm = None
