# Prueba: abre MT5 en la cuenta, pone el historial a la vista y manda al bot la captura de esa tabla.
import time

import captura
from lector import conectar


def main():
    import MetaTrader5 as mt5
    if not conectar(mt5):
        raise SystemExit('MT5 no conecta')
    try:
        time.sleep(8)
        imagen = captura.historial()
        print('captura:', imagen.size, flush=True)
        print('enviada:', captura.mandar(captura.png_de(imagen)))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
