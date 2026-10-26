"""Pequena interfaz para controlar dos triggers TTL en Arduino UNO.

Requiere:
    pip install pyserial

El Arduino debe tener cargado trigger_ttl_controller.ino.
"""

import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError as exc:
    raise SystemExit(
        "Falta pyserial. Instala con: pip install pyserial"
    ) from exc


BAUDRATE = 9600


def to_microseconds(value: str, unit: str) -> int:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError("La duración debe ser un número.") from exc

    if number < 0:
        raise ValueError("La duración no puede ser negativa.")

    factors = {
        "µs": 1,
        "ms": 1_000,
        "s": 1_000_000,
    }
    result = int(round(number * factors[unit]))

    # El firmware usa comparaciones seguras con uint32_t hasta ~2^31 us.
    if result > 2_000_000_000:
        raise ValueError("Duración demasiado grande (máximo práctico ~2000 s).")
    return result


class TriggerTTLApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Trigger TTL - Arduino UNO")
        self.geometry("720x610")
        self.minsize(700, 580)

        self.ser = None
        self.reader_thread = None
        self.stop_reader = threading.Event()
        self.rx_queue = queue.Queue()

        self.port_var = tk.StringVar()
        self.connection_var = tk.StringVar(value="Desconectado")

        self.enable12_var = tk.BooleanVar(value=True)
        self.enable10_var = tk.BooleanVar(value=True)
        self.duration12_var = tk.StringVar(value="10")
        self.duration10_var = tk.StringVar(value="10")
        self.unit12_var = tk.StringVar(value="ms")
        self.unit10_var = tk.StringVar(value="ms")

        self.buzzer_var = tk.BooleanVar(value=True)
        self.buzzer_duration_var = tk.StringVar(value="5")
        self.buzzer_unit_var = tk.StringVar(value="ms")

        self._build_ui()
        self.refresh_ports()
        self.after(50, self._drain_rx_queue)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 7}

        connection = ttk.LabelFrame(self, text="Conexión")
        connection.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(connection, text="Puerto COM:").grid(row=0, column=0, **pad)
        self.port_combo = ttk.Combobox(
            connection, textvariable=self.port_var, state="readonly", width=34
        )
        self.port_combo.grid(row=0, column=1, sticky="ew", **pad)

        ttk.Button(connection, text="Actualizar", command=self.refresh_ports).grid(
            row=0, column=2, **pad
        )
        self.connect_button = ttk.Button(
            connection, text="Conectar", command=self.toggle_connection
        )
        self.connect_button.grid(row=0, column=3, **pad)

        ttk.Label(connection, textvariable=self.connection_var).grid(
            row=1, column=0, columnspan=4, sticky="w", **pad
        )
        connection.columnconfigure(1, weight=1)

        pulse = ttk.LabelFrame(self, text="Pulsos TTL")
        pulse.pack(fill="x", padx=12, pady=6)

        ttk.Label(pulse, text="Canal").grid(row=0, column=0, **pad)
        ttk.Label(pulse, text="Habilitar").grid(row=0, column=1, **pad)
        ttk.Label(pulse, text="Duración").grid(row=0, column=2, **pad)
        ttk.Label(pulse, text="Unidad").grid(row=0, column=3, **pad)
        ttk.Label(pulse, text="Manual").grid(row=0, column=4, columnspan=2, **pad)

        ttk.Label(pulse, text="Pin 12").grid(row=1, column=0, **pad)
        ttk.Checkbutton(pulse, variable=self.enable12_var).grid(row=1, column=1, **pad)
        ttk.Entry(pulse, textvariable=self.duration12_var, width=15).grid(
            row=1, column=2, **pad
        )
        ttk.Combobox(
            pulse,
            textvariable=self.unit12_var,
            values=("µs", "ms", "s"),
            state="readonly",
            width=7,
        ).grid(row=1, column=3, **pad)
        ttk.Button(pulse, text="HIGH", command=lambda: self.manual_out(12, 1)).grid(
            row=1, column=4, **pad
        )
        ttk.Button(pulse, text="LOW", command=lambda: self.manual_out(12, 0)).grid(
            row=1, column=5, **pad
        )

        ttk.Label(pulse, text="Pin 10").grid(row=2, column=0, **pad)
        ttk.Checkbutton(pulse, variable=self.enable10_var).grid(row=2, column=1, **pad)
        ttk.Entry(pulse, textvariable=self.duration10_var, width=15).grid(
            row=2, column=2, **pad
        )
        ttk.Combobox(
            pulse,
            textvariable=self.unit10_var,
            values=("µs", "ms", "s"),
            state="readonly",
            width=7,
        ).grid(row=2, column=3, **pad)
        ttk.Button(pulse, text="HIGH", command=lambda: self.manual_out(10, 1)).grid(
            row=2, column=4, **pad
        )
        ttk.Button(pulse, text="LOW", command=lambda: self.manual_out(10, 0)).grid(
            row=2, column=5, **pad
        )

        ttk.Separator(pulse, orient="horizontal").grid(
            row=3, column=0, columnspan=6, sticky="ew", padx=10, pady=5
        )

        self.fire_button = ttk.Button(
            pulse, text="DISPARAR PULSOS", command=self.fire_pulse
        )
        self.fire_button.grid(row=4, column=0, columnspan=4, sticky="ew", padx=10, pady=10)

        ttk.Button(pulse, text="Reset salidas", command=self.reset_outputs).grid(
            row=4, column=4, columnspan=2, sticky="ew", padx=10, pady=10
        )

        buzzer = ttk.LabelFrame(self, text="Buzzer - pin 13")
        buzzer.pack(fill="x", padx=12, pady=6)

        ttk.Checkbutton(
            buzzer,
            text="Activar buzzer al terminar el pulso",
            variable=self.buzzer_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w", **pad)

        ttk.Label(buzzer, text="Duración buzzer:").grid(row=1, column=0, **pad)
        ttk.Entry(buzzer, textvariable=self.buzzer_duration_var, width=15).grid(
            row=1, column=1, **pad
        )
        ttk.Combobox(
            buzzer,
            textvariable=self.buzzer_unit_var,
            values=("µs", "ms", "s"),
            state="readonly",
            width=7,
        ).grid(row=1, column=2, **pad)
        ttk.Button(buzzer, text="Probar buzzer", command=self.test_buzzer).grid(
            row=1, column=3, **pad
        )

        log_frame = ttk.LabelFrame(self, text="Monitor serial")
        log_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        self.log = tk.Text(log_frame, height=12, state="disabled", wrap="word")
        self.log.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.log.configure(yscrollcommand=scrollbar.set)

    def append_log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{timestamp}] {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_ports(self):
        ports = list(list_ports.comports())
        display_values = [f"{p.device} — {p.description}" for p in ports]
        self.port_combo["values"] = display_values

        if display_values:
            current = self.port_var.get()
            if current not in display_values:
                # Prioriza dispositivos que parezcan Arduino/USB serial.
                preferred = next(
                    (
                        value
                        for value in display_values
                        if "arduino" in value.lower()
                        or "ch340" in value.lower()
                        or "usb serial" in value.lower()
                    ),
                    display_values[0],
                )
                self.port_var.set(preferred)
        else:
            self.port_var.set("")

    def _selected_port(self) -> str:
        selection = self.port_var.get().strip()
        if not selection:
            raise ValueError("Selecciona un puerto COM.")
        return selection.split(" — ", 1)[0]

    def toggle_connection(self):
        if self.ser and self.ser.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        try:
            port = self._selected_port()
            self.ser = serial.Serial(port, BAUDRATE, timeout=0.1, write_timeout=1)
            # Arduino UNO suele reiniciarse al abrir el puerto.
            time.sleep(1.8)
            self.ser.reset_input_buffer()

            self.stop_reader.clear()
            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()

            self.connection_var.set(f"Conectado a {port} @ {BAUDRATE} baud")
            self.connect_button.configure(text="Desconectar")
            self.append_log(f"Conectado a {port}")
            self.send_command("PING")
        except Exception as exc:
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            messagebox.showerror("Conexión", str(exc))

    def disconnect(self):
        self.stop_reader.set()
        if self.ser:
            try:
                if self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.connection_var.set("Desconectado")
        self.connect_button.configure(text="Conectar")
        self.append_log("Puerto desconectado")

    def _reader_loop(self):
        while not self.stop_reader.is_set():
            try:
                if not self.ser or not self.ser.is_open:
                    break
                raw = self.ser.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        self.rx_queue.put(line)
            except Exception as exc:
                if not self.stop_reader.is_set():
                    self.rx_queue.put(f"[ERROR SERIAL] {exc}")
                break

    def _drain_rx_queue(self):
        try:
            while True:
                self.append_log("Arduino > " + self.rx_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(50, self._drain_rx_queue)

    def send_command(self, command: str):
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Arduino no está conectado.")
        self.ser.write((command + "\n").encode("ascii"))
        self.ser.flush()
        self.append_log("PC > " + command)

    def fire_pulse(self):
        try:
            d12 = (
                to_microseconds(self.duration12_var.get(), self.unit12_var.get())
                if self.enable12_var.get()
                else 0
            )
            d10 = (
                to_microseconds(self.duration10_var.get(), self.unit10_var.get())
                if self.enable10_var.get()
                else 0
            )

            if d12 == 0 and d10 == 0:
                raise ValueError("Habilita al menos uno de los dos canales.")

            buzzer_us = to_microseconds(
                self.buzzer_duration_var.get(), self.buzzer_unit_var.get()
            )
            buzzer_enabled = 1 if self.buzzer_var.get() else 0

            self.send_command(f"PULSE,{d12},{d10},{buzzer_enabled},{buzzer_us}")
        except Exception as exc:
            messagebox.showerror("Pulso", str(exc))

    def manual_out(self, pin: int, state: int):
        try:
            self.send_command(f"OUT,{pin},{state}")
        except Exception as exc:
            messagebox.showerror("Salida manual", str(exc))

    def reset_outputs(self):
        try:
            self.send_command("RESET")
        except Exception as exc:
            messagebox.showerror("Reset", str(exc))

    def test_buzzer(self):
        try:
            buzzer_us = to_microseconds(
                self.buzzer_duration_var.get(), self.buzzer_unit_var.get()
            )
            self.send_command(f"BEEP,{buzzer_us}")
        except Exception as exc:
            messagebox.showerror("Buzzer", str(exc))

    def on_close(self):
        self.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = TriggerTTLApp()
    app.mainloop()
