"""Pruebas de protocolo sin conectar ni accionar hardware real."""
import unittest
from collections import deque
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trigger import TriggerController

class FakePort:
    def __init__(self):
        self.is_open = True
        self.responses = deque([b"READY,TRIGGER_TTL_V1\n"])
        self.sent = []

    def readline(self):
        return self.responses.popleft() if self.responses else b""

    def read_all(self):
        results = b"".join(self.responses)
        self.responses.clear()
        return results

    def reset_input_buffer(self):
        self.responses.clear()

    def reset_output_buffer(self):
        pass

    @property
    def in_waiting(self):
        return sum(len(response) for response in self.responses)

class FakeDevice:
    def __init__(self):
        self.port = FakePort()
        self._connected = False

    @property
    def connected(self):
        return self._connected

    def open(self, port, baudrate):
        self._connected = True
        self.port.is_open = True

    def write(self, data):
        self.port.sent.append(data)
        if data == b"PING\n":
            self.port.responses.append(b"PONG\n")
        elif data.startswith(b"PULSE,"):
            self.port.responses.append(b"OK,PULSE\n")
        elif data == b"RESET\n":
            self.port.responses.append(b"OK,RESET\n")
        elif data == b"STATUS\n":
            self.port.responses.append(b"STATUS,D12=0,D10=0,BUZZER=0,P12_ACTIVE=0,P10_ACTIVE=0\n")

    def close(self):
        self._connected = False
        self.port.is_open = False

class TestArduinoV1(unittest.TestCase):
    def test_identifies_and_acks_arduino_firmware(self):
        with patch('trigger.SerialDevice', FakeDevice):
            controller = TriggerController()
            self.assertIn('Arduino UNO TTL V1', controller.connect('COM_FAKE'))
            self.assertEqual(controller.mode, 'v1')
            self.assertEqual(controller.start(10000, 5000), 'OK,PULSE')
            self.assertIn(b'PULSE,10000,5000,0,0\n', controller.device.port.sent)
            self.assertEqual(controller.stop(), 'OK,RESET')
            controller.close()

    def test_prevents_zero_pulse(self):
        with patch('trigger.SerialDevice', FakeDevice):
            controller = TriggerController()
            controller.connect('COM_FAKE')
            with self.assertRaises(ValueError):
                controller.start(0, 0)
            self.assertFalse(any(x.startswith(b'PULSE,') for x in controller.device.port.sent))
            controller.close()

if __name__ == '__main__':
    unittest.main()
