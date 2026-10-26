"""Captura binaria transparente y con marcas temporales para estudiar Hentschel 373.

IMPORTANTE: no interpreta bytes ni inventa un protocolo ausente del video.
No transmite comandos. Preserva hex, longitud y monotonic_ns.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time


def capture_raw(port, baudrate, output_jsonl, seconds=10.0, serial_factory=None):
    if serial_factory is None:
        from serial import Serial as serial_factory
    target = Path(output_jsonl)
    if target.exists():
        raise FileExistsError(f'El archivo de captura ya existe: {target}')
    if float(seconds) <= 0:
        raise ValueError('Duración inválida')
    target.parent.mkdir(parents=True, exist_ok=True)
    received = 0
    with serial_factory(port=port, baudrate=int(baudrate), timeout=0.15) as s:
        deadline = time.monotonic() + float(seconds)
        with target.open('x', encoding='utf-8') as out:
            while time.monotonic() < deadline:
                chunk = s.read(max(1, min(int(getattr(s, 'in_waiting', 0) or 1), 4096)))
                if not chunk:
                    continue
                record = {'utc':datetime.now(timezone.utc).isoformat(),
                          'monotonic_ns':time.monotonic_ns(), 'byte_count':len(chunk),
                          'hex':chunk.hex().upper(), 'port':str(port), 'baudrate':int(baudrate)}
                out.write(json.dumps(record, ensure_ascii=False)+'\n')
                out.flush()
                received += len(chunk)
    return {'bytes':received, 'path':str(target)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Solo escucha Hentschel; NUNCA envía comandos')
    p.add_argument('--puerto', required=True)
    p.add_argument('--baudios', type=int, required=True)
    p.add_argument('--segundos', type=float, default=10)
    p.add_argument('--salida', default='captura_hentschel.jsonl')
    a = p.parse_args()
    print(capture_raw(a.puerto, a.baudios, a.salida, a.segundos))
