"""Conector genérico para el LSV. TCP es una aproximación no vista completa en video."""
import socket
import threading
import time
from serial_device import SerialDevice
from config import LASER_RESPONSE_DELAY_SECONDS

class LSVConnection:
    def __init__(self):
        self.serial = SerialDevice()
        self.tcp = None
        self.lock = threading.RLock()
        self.transport = None

    @property
    def connected(self):
        return self.serial.connected if self.transport == "RS232" else self.tcp is not None

    def open_serial(self, port, baudrate=9600):
        self.close()
        self.serial.open(port, baudrate=baudrate)
        self.transport = "RS232"

    def open_tcp(self, host, port, timeout=2):
        self.close()
        self.tcp = socket.create_connection((host, int(port)), timeout=timeout)
        self.tcp.settimeout(0.3)
        self.transport = "TCP"

    def write(self, data):
        if not self.connected:
            raise RuntimeError("LSV sin conexión")
        data = data.encode("ascii") if isinstance(data, str) else data
        if self.transport == "RS232":
            self.serial.write(data)
        else:
            with self.lock:
                self.tcp.sendall(data)

    def query_laser(self, command):
        if not self.connected:
            raise RuntimeError("LSV sin conexión")
        if self.transport == "RS232":
            return self.serial.query_laser(command)
        with self.lock:
            self.tcp.sendall((command + "\r").encode("ascii"))
            response = bytearray()
            deadline = time.monotonic() + 1.0
            last_byte = None
            while time.monotonic() < deadline:
                try:
                    part = self.tcp.recv(4096)
                    if not part:
                        raise ConnectionError("Conexión TCP cerrada")
                    response.extend(part)
                    last_byte = time.monotonic()
                except socket.timeout:
                    if response and last_byte and time.monotonic() - last_byte > LASER_RESPONSE_DELAY_SECONDS:
                        break
            return response.decode("ascii", errors="replace").strip()

    def close(self):
        self.serial.close()
        if self.tcp is not None:
            try:
                self.tcp.close()
            finally:
                self.tcp = None
        self.transport = None
