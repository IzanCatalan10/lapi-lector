# Captura de pantalla REAL del terminal de MetaTrader 5 con el historial a la vista, para acompañar el aviso de una
# operación cerrada. No se dibuja nada: es lo que enseña el propio MetaTrader en la máquina que vigila la cuenta.
import ctypes
import io
import json
import os
import re
import time
import urllib.request
from ctypes import wintypes

user32 = ctypes.windll.user32
SW_MAXIMIZE = 3
WM_COMMAND = 0x0111


def ventanas():
    """Ventanas de primer nivel visibles: (hwnd, clase, título)."""
    lista = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            clase = ctypes.create_unicode_buffer(256)
            titulo = ctypes.create_unicode_buffer(512)
            user32.GetClassNameW(hwnd, clase, 256)
            user32.GetWindowTextW(hwnd, titulo, 512)
            lista.append((hwnd, clase.value, titulo.value))
        return True

    user32.EnumWindows(cada, 0)
    return lista


def hijas(hwnd):
    lista = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cada(h, _):
        clase = ctypes.create_unicode_buffer(256)
        titulo = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, clase, 256)
        user32.GetWindowTextW(h, titulo, 256)
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        lista.append((h, clase.value, titulo.value, (r.left, r.top, r.right, r.bottom), bool(user32.IsWindowVisible(h))))
        return True

    user32.EnumChildWindows(hwnd, cada, 0)
    return lista


def terminal():
    for hwnd, clase, _ in ventanas():
        if clase.startswith('MetaQuotes::MetaTrader'):
            return hwnd
    return None


def sin_numeros_largos(t):
    """Para los registros públicos: fuera números de cuenta."""
    return re.sub(r'\d{5,}', '#', t)


def al_frente(hwnd):
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.5)


def pantalla():
    from PIL import ImageGrab
    return ImageGrab.grab(all_screens=False)


def png_de(imagen):
    salida = io.BytesIO()
    imagen.save(salida, format='PNG', optimize=True)
    return salida.getvalue()


def mandar(png, posiciones=()):
    url = os.environ['BOT_URL'].rstrip('/') + '/captura'
    if posiciones:
        url += '?posiciones=' + ','.join(str(p) for p in posiciones)
    peticion = urllib.request.Request(url, data=png, method='POST', headers={
        'content-type': 'image/png', 'authorization': 'Bearer ' + os.environ['INGESTA_CLAVE'], 'user-agent': 'lector-mt5',
    })
    with urllib.request.urlopen(peticion, timeout=40) as r:
        # Solo el nombre del fichero: la dirección del bot no sale en los registros.
        return json.loads(r.read()).get('url', '').rsplit('/', 1)[-1]
