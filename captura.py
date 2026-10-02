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


SW_HIDE = 0
TCM_FIRST = 0x1300
TCM_GETITEMCOUNT = TCM_FIRST + 4
TCM_SETCURFOCUS = TCM_FIRST + 48
WM_KEYDOWN, WM_KEYUP, VK_END = 0x0100, 0x0101, 0x23
# Pestañas de la Caja de herramientas del terminal, por orden: Trade, Exposure, History, News, Mailbox...
PESTANA_HISTORIAL = 2


def caja_de_herramientas(hwnd):
    """(pestañas, tabla) de la Caja de herramientas: lo que hay dentro del panel "Toolbox"."""
    todas = hijas(hwnd)
    caja = next((h for h in todas if h[2] == 'Toolbox'), None)
    if not caja:
        return None, None
    _, _, _, (izq, arr, der, aba), _ = caja
    dentro = [h for h in todas if h[4] and h[3][0] >= izq and h[3][1] >= arr - 2 and h[3][2] <= der and h[3][3] <= aba + 2]
    pestanas = max((h for h in dentro if h[1] == 'SysTabControl32'), key=lambda h: h[3][2] - h[3][0], default=None)
    tabla = max((h for h in dentro if h[1] == 'SysListView32'), key=lambda h: (h[3][2] - h[3][0]) * (h[3][3] - h[3][1]), default=None)
    return pestanas, tabla


def historial():
    """Pone la pestaña History a la vista, baja hasta lo último y devuelve la captura de esa tabla (solo la tabla:
    ni título de la ventana, ni buzón, ni nada que lleve el número de cuenta o nombres)."""
    hwnd = terminal()
    if not hwnd:
        raise RuntimeError('no encuentro la ventana del terminal')
    al_frente(hwnd)
    # La ventanita de consejos que el terminal abre encima: fuera.
    for h, clase, _, _, visible in hijas(hwnd):
        if visible and clase.startswith('Chrome_WidgetWin'):
            padre = user32.GetParent(user32.GetParent(h)) or user32.GetParent(h)
            user32.ShowWindow(padre, SW_HIDE)
    pestanas, _ = caja_de_herramientas(hwnd)
    if not pestanas:
        raise RuntimeError('no encuentro la Caja de herramientas')
    if user32.SendMessageW(pestanas[0], TCM_GETITEMCOUNT, 0, 0) <= PESTANA_HISTORIAL:
        raise RuntimeError('la Caja de herramientas no tiene pestaña de historial')
    user32.SendMessageW(pestanas[0], TCM_SETCURFOCUS, PESTANA_HISTORIAL, 0)
    time.sleep(4)
    pestanas, tabla = caja_de_herramientas(hwnd)
    if not tabla:
        raise RuntimeError('no encuentro la tabla del historial')
    user32.PostMessageW(tabla[0], WM_KEYDOWN, VK_END, 0)
    user32.PostMessageW(tabla[0], WM_KEYUP, VK_END, 0)
    time.sleep(1.5)
    return pantalla().crop(tabla[3])


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
