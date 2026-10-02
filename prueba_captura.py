# Prueba: abre MT5 en la cuenta, enseña qué ventanas y controles tiene el terminal y manda una captura al bot.
import time

import captura
from lector import conectar


def main():
    import MetaTrader5 as mt5
    if not conectar(mt5):
        raise SystemExit('MT5 no conecta')
    try:
        time.sleep(8)
        hwnd = captura.terminal()
        print('terminal encontrado:', bool(hwnd), flush=True)
        if not hwnd:
            for _, clase, titulo in captura.ventanas():
                print('  ventana:', clase, '|', captura.sin_numeros_largos(titulo))
            raise SystemExit('no encuentro la ventana del terminal')
        captura.al_frente(hwnd)
        for h, clase, titulo, rect, visible in captura.hijas(hwnd):
            if visible:
                print(f'  {clase} | {captura.sin_numeros_largos(titulo)[:40]} | {rect}')
        imagen = captura.pantalla()
        print('pantalla:', imagen.size, flush=True)
        print('enviada:', captura.mandar(captura.png_de(imagen)))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
