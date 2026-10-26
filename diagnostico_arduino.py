"""Diagnóstico seguro por defecto: PING, STATUS (sin generar pulsos).

Ejecutar con: python diagnostico_arduino.py COM6
Para mandar un pulso se requiere --pulso-d12-us / --pulso-d10-us y
una confirmación manual explícita, con salidas físicas desconectadas.
"""
import argparse
from trigger import TriggerController


def main():
    p=argparse.ArgumentParser(description='Arduino Uno TTL V1 · diagnóstico')
    p.add_argument('puerto', help='Puerto COM del Arduino, ej. COM6')
    p.add_argument('--pulso-d12-us',type=int,default=0)
    p.add_argument('--pulso-d10-us',type=int,default=0)
    args=p.parse_args()
    c=TriggerController()
    try:
        print('Reconocimiento:',c.connect(args.puerto))
        print('Estado:',c.status())
        if args.pulso_d12_us or args.pulso_d10_us:
            respuesta=input('Hay una SALIDA TTL FÍSICA de 5V. ¿Aislaste los instrumentos? Escribe DISPARAR: ')
            if respuesta != 'DISPARAR':
                print('Disparo cancelado por usuario')
                return
            print('ACK:',c.start(args.pulso_d12_us,args.pulso_d10_us))
            print('ACK solo confirma comando serial, NO tiempo del pulso')
            print('RESET:',c.stop())
    finally:
        c.close()

if __name__=='__main__':
    main()
