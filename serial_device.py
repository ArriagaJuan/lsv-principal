"""Acceso exclusivo a puerto serie para láser RS-232 y trigger."""
import threading
import time
from config import LASER_RESPONSE_DELAY_SECONDS

class SerialDevice:
    def __init__(self):
        self.port = None
        self.lock = threading.RLock()

    @property
    def connected(self):
        return self.port is not None and self.port.is_open

    @property
    def port_name(self):
        return str(self.port.port) if self.connected else None

    def open(self, name, baudrate=9600, timeout=0.2):
        import serial
        self.close()
        self.port = serial.Serial(name, int(baudrate), timeout=timeout, write_timeout=1)

    def write(self, data):
        if not self.connected:
            raise RuntimeError("El puerto no está conectado")
        if isinstance(data, str):
            data = data.encode("ascii")
        with self.lock:
            self.port.write(data)
            self.port.flush()

    def query_laser(self, command):
        """Lee respuesta del láser; lógica de final de ráfaga reconstruida del video."""
        if not self.connected:
            raise RuntimeError("El lector RS-232 no está conectado")
        with self.lock:
            self.port.reset_input_buffer()
            self.port.write((command + "\r").encode("ascii"))
            self.port.flush()
            started = time.monotonic()
            deadline = started + max(0.5, float(self.port.timeout or 0) * 2)
            response = bytearray()
            last_byte_at = None
            while time.monotonic() < deadline:
                waiting = int(self.port.in_waiting)
                if waiting:
                    response.extend(self.port.read(waiting))
                    last_byte_at = time.monotonic()
                elif response and last_byte_at and time.monotonic() - last_byte_at > LASER_RESPONSE_DELAY_SECONDS:
                    break
                else:
                    time.sleep(0.005)
            return response.decode("ascii", errors="replace").strip()

    def close(self):
        with self.lock:
            if self.port is not None:
                try:
                    self.port.close()
                finally:
                    self.port = None
