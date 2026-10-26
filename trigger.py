"""Control comprobable del firmware ORIGINAL TTL V1 para Arduino Uno.

NO aplica el protocolo Kistler V2/V3 visible en otros fotogramas: el usuario
confirmó que el hardware usa el firmware TTL V1 recuperado.

Protocolo real de trigger_ttl_controller.ino: 9600 8N1, LF,
PING -> PONG; STATUS -> STATUS,D12=...; PULSE,d12,d10,buzzer,beep -> OK,PULSE;
RESET -> OK,RESET. La respuesta OK,PULSE solo confirma la recepción de la
orden, NO la hora del flanco ni la precisión temporal del pulso.
"""
from __future__ import annotations
import re
import threading
import time
from serial_device import SerialDevice

MAX_DURATION_US = 1_000_000  # margen conservador en la interfaz recuperada
_STATUS = re.compile(r"^STATUS,D12=[01],D10=[01],BUZZER=[01],P12_ACTIVE=[01],P10_ACTIVE=[01]$")


class TriggerController:
    def __init__(self, device=None):
        self.device = device if device is not None else SerialDevice()
        self.mode = None
        self.lock = threading.RLock()
        self.last_command_monotonic_ns = None
        self.last_ack_monotonic_ns = None
        self.last_command = ""

    @property
    def connected(self):
        return bool(self.device.connected) and self.mode == "v1"

    def _query(self, command, expected, seconds=1.5):
        """Un envío de comandos físicos, SIN reintentos automáticos.

        Respuestas READY o DONE rezagadas son informativas; error ERR falla.
        """
        with self.lock:
            if not self.device.connected:
                raise RuntimeError("Puerto del Arduino desconectado")
            raw = (command + "\n").encode("ascii")
            port = self.device.port
            port.reset_input_buffer()
            self.last_command = command
            self.last_command_monotonic_ns = time.monotonic_ns()
            self.last_ack_monotonic_ns = None
            self.device.write(raw)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                reply = port.readline().decode("ascii", errors="replace").strip()
                if not reply:
                    continue
                if reply.startswith("ERR,"):
                    raise RuntimeError(f"Arduino rechazó {command.split(',')[0]}: {reply}")
                if expected(reply):
                    self.last_ack_monotonic_ns = time.monotonic_ns()
                    return reply
            raise TimeoutError(f"Arduino no confirmó {command.split(',')[0]} en {seconds} s; "
                               "NO se reintentó automáticamente para evitar doble disparo")

    def connect(self, port):
        with self.lock:
            self.close()
            self.device.open(port, 9600)
            try:
                # Arduino Uno suele resetearse al abrir el puerto. PING es seguro reintentar.
                deadline = time.monotonic() + 4.5
                while time.monotonic() < deadline:
                    try:
                        self._query("PING", lambda response: response == "PONG", seconds=0.35)
                        break
                    except TimeoutError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("No se detectó el firmware TTL V1 (respuesta PONG a 9600 baud)")
                self.mode = "v1"
                state = self.status()
                if not _STATUS.fullmatch(state):
                    raise RuntimeError(f"La respuesta STATUS no coincide con el TTL V1: {state!r}")
                # La conexión deja explícitamente las salidas en LOW.
                self.stop()
                return f"Arduino UNO TTL V1 · 9600 baud · {port} · D12/D10"
            except Exception:
                self.mode = None
                self.device.close()
                raise

    def status(self):
        if not self.connected:
            raise RuntimeError("Arduino TTL V1 no conectado")
        return self._query("STATUS", lambda s: bool(_STATUS.fullmatch(s)))

    @staticmethod
    def _duration(us, label):
        if isinstance(us, bool):
            raise ValueError(f"{label}: duración inválida")
        if isinstance(us, float) and not us.is_integer():
            raise ValueError(f"{label}: especifica microsegundos enteros")
        try:
            value = int(us)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"{label}: duración inválida") from exc
        if not 0 <= value <= MAX_DURATION_US:
            raise ValueError(f"{label}: duración debe ser entre 0 y {MAX_DURATION_US} µs")
        return value

    def start(self, duration_us_12=0, duration_us_10=0):
        if not self.connected:
            raise RuntimeError("Arduino no conectado o no reconocido")
        d12 = self._duration(duration_us_12, "D12")
        d10 = self._duration(duration_us_10, "D10")
        if not (d12 or d10):
            raise ValueError("Configura al menos un canal del trigger con duración distinta de 0")
        return self._query(f"PULSE,{d12},{d10},0,0", lambda s: s == "OK,PULSE", seconds=2)

    # Alias compatibles con el módulo del 21 de octubre.
    def request_start(self, duration_us_12=0, duration_us_10=0):
        return self.start(duration_us_12, duration_us_10)

    def wait_start_confirmation(self, seconds=2):
        # La confirmación se verifica sincrónicamente dentro de request_start.
        return "OK,PULSE" if self.last_ack_monotonic_ns is not None and self.last_command.startswith("PULSE,") else None

    def stop(self):
        if not self.device.connected:
            return None
        return self._query("RESET", lambda s: s == "OK,RESET", seconds=2)

    def request_stop(self):
        return self.stop()

    def wait_stop_confirmation(self, seconds=2):
        return "OK,RESET" if self.last_ack_monotonic_ns is not None and self.last_command == "RESET" else None

    def close(self):
        with self.lock:
            if self.device.connected:
                try:
                    self.stop()
                except Exception:
                    pass  # cerrar puerto incluso si la conexión falla; verificar LOW físicamente
            self.mode = None
            self.device.close()
