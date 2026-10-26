"""Persistencia exclusiva de configuración del usuario; no contiene credenciales."""
from pathlib import Path
import json

DEFAULTS = {
    "lsv_host": "192.168.1.100",
    "lsv_port": 10001,
    "lsv_daq_mode": 252,
    "lsv_daq_divisor": 16,
    "lsv_average_samples": 100,
    "lsv_reset_accumulator": False,
    "lsv_serial": "",
    "lsv_connection": "TCP",  # TCP o RS232
    "lsv_temperature_source": "Crudo",
    "lsv_temperature_c": 20,
    "reader_port": "COM5",
    "trigger_port": "COM6",
    "trigger_d12_us": 0,
    "trigger_d10_us": 0,
    "export_directory": str(Path.home() / "Documents" / "exportaciones_lsv"),
    "auto_retry": True,
}

class ConfigStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).with_name("config_ligero.json")
        self.data = dict(DEFAULTS)
        if self.path.exists():
            try:
                parsed = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    self.data.update({k: v for k, v in parsed.items() if k in DEFAULTS})
            except (OSError, ValueError):
                pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def update(self, values):
        self.data.update({k: v for k, v in values.items() if k in DEFAULTS})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)
