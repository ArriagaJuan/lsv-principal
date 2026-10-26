"""Prueba rápida sin hardware ni PySide6: genera un Excel de datos FICTICIOS."""
from datetime import datetime
from pathlib import Path
from exporter import export_records
from measurements import integrate_distance


def main():
    rows = []
    distance = 0.0
    for cycle in range(1, 4):
        for i in range(11):
            t = i * 0.5
            speed = 1200.0 + i * 0.5
            if i:
                distance = integrate_distance(t - 0.5, speed - 0.5, t, speed, distance)
            rows.append(dict(cycle=cycle,attempt=1,time_s=t,raw_time_s=t,
                             velocity_m_min=speed,distance_m=distance))
        distance = 0
    outfile = export_records(rows, output_directory=Path(__file__).with_name('exportaciones_ejemplo'),
                             metadata={'Origen':'SIMULADO - NO USAR EN CALIBRACIÓN', 'Generado':datetime.now().isoformat()})
    print('Prueba completada, Excel de EJEMPLO:', outfile)

if __name__ == '__main__':
    main()
