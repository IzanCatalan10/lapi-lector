# Lee una cuenta de MT5 con la contraseña de INVERSOR (solo lectura: no puede operar) y manda a un bot la foto de la
# cuenta y los movimientos de los últimos 45 días. Corre en una máquina de GitHub Actions, para que no haga falta
# ningún ordenador encendido.
#
#   python lector.py una       una lectura y fuera
#   python lector.py vigilar   se queda con MT5 abierto durante el horario de mercado, mira cada 20 segundos y avisa
#                              al bot en cuanto cambia algo (una operación que se cierra), y cada 5 minutos aunque no
#                              cambie nada (para que el bot sepa que sigue vivo). Justo después del cierre (23:00 en
#                              España) manda la lectura del día.
#
# Todo lo propio va en secretos del repositorio, nada en el código: MT5_CUENTA, MT5_SERVIDOR, MT5_CLAVE (contraseña
# de inversor), BOT_URL e INGESTA_CLAVE (la que pide el bot en /ingesta).
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BOT = os.environ['BOT_URL'].rstrip('/')
CUENTA = int(os.environ['MT5_CUENTA'])
SERVIDOR = os.environ['MT5_SERVIDOR']
TERMINAL = r'C:\Program Files\MetaTrader 5\terminal64.exe'
DIAS = 45
MADRID = ZoneInfo('Europe/Madrid')
# El servidor del bróker va en hora de Europa del Este: UTC+3 en verano, UTC+2 en invierno.
DESFASE_VERANO_H = 3
# Horario en el que merece la pena vigilar (hora de España, de lunes a viernes).
ABRE = (8, 0)
CIERRA = (23, 0)
# Un trabajo de GitHub dura como mucho 6 horas: se deja antes y el siguiente toma el relevo.
MAX_VIGILANCIA = 5 * 3600 + 35 * 60
CADA = 20
LATIDO = 300


def pedir(ruta, cuerpo=None):
    peticion = urllib.request.Request(
        BOT + ruta, data=json.dumps(cuerpo).encode() if cuerpo is not None else None, method='POST' if cuerpo is not None else 'GET',
        headers={'content-type': 'application/json', 'authorization': 'Bearer ' + os.environ['INGESTA_CLAVE'], 'user-agent': 'lector-mt5'},
    )
    with urllib.request.urlopen(peticion, timeout=30) as r:
        return json.loads(r.read())


def ultimo_domingo(anio, mes):
    d = datetime(anio, mes, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def desfase_servidor(mt5, simbolo):
    """Segundos que el reloj del servidor va por delante de UTC: se saca del último precio (redondeado a media hora).
    Con el mercado cerrado el último precio es viejo: entonces se deduce del cambio de hora europeo."""
    tick = mt5.symbol_info_tick(simbolo) if simbolo else None
    if tick and tick.time:
        diferencia = tick.time - time.time()
        redondeado = round(diferencia / 1800) * 1800
        if abs(diferencia - redondeado) < 600 and abs(redondeado) <= 14 * 3600:
            return redondeado
    hoy = datetime.utcnow()
    verano = ultimo_domingo(hoy.year, 3) <= hoy < ultimo_domingo(hoy.year, 10)
    return (DESFASE_VERANO_H if verano else DESFASE_VERANO_H - 1) * 3600


def conectar(mt5):
    for intento in range(3):
        if mt5.initialize(path=TERMINAL, portable=True, login=CUENTA, password=os.environ['MT5_CLAVE'], server=SERVIDOR, timeout=120000):
            info = mt5.account_info()
            if info is not None and info.login == CUENTA:
                return True
        print(f'intento {intento + 1}: MT5 no conecta: {mt5.last_error()[0]}', flush=True)
        mt5.shutdown()
        time.sleep(20)
    return False


def leer(mt5):
    """La lectura tal como la quiere el bot, o None si MT5 no contesta."""
    info = mt5.account_info()
    if info is None or info.login != CUENTA:
        return None
    deals = mt5.history_deals_get(datetime.now() - timedelta(days=DIAS), datetime.now() + timedelta(days=2))
    if deals is None:
        return None
    simbolos = [d.symbol for d in deals if d.symbol]
    desfase = desfase_servidor(mt5, simbolos[-1] if simbolos else None)
    tipos = {0: 'buy', 1: 'sell', 2: 'saldo'}
    entradas = {0: 'in', 1: 'out', 2: 'out', 3: 'out'}
    return {
        'cuenta': info.login, 'balance': info.balance, 'equity': info.equity, 'moneda': info.currency, 't': int(time.time()),
        'deals': [{
            'ticket': d.ticket, 'posicion': d.position_id, 't': d.time - desfase,
            'tipo': tipos.get(d.type, 'otro'), 'entrada': entradas.get(d.entry, 'otro'),
            'simbolo': d.symbol, 'volumen': d.volume, 'precio': d.price,
            'beneficio': d.profit, 'swap': d.swap, 'comision': d.commission + getattr(d, 'fee', 0.0),
        } for d in deals],
    }


def leer_con_historial(mt5):
    """Recién conectado, el historial puede tardar unos segundos en bajar."""
    for _ in range(15):
        cuerpo = leer(mt5)
        if cuerpo and cuerpo['deals']:
            return cuerpo
        time.sleep(3)
    return None


def enviar(cuerpo, motivo):
    cuerpo['t'] = int(time.time())
    try:
        respuesta = pedir('/ingesta', cuerpo)
    except Exception as e:  # un corte de red no tumba la vigilancia: a los 20 segundos se vuelve a intentar
        print(f'{datetime.now(MADRID):%H:%M:%S} no se pudo enviar ({motivo}): {type(e).__name__}', flush=True)
        return False
    print(f"{datetime.now(MADRID):%H:%M:%S} enviado ({motivo}): {len(cuerpo['deals'])} movimientos, ok={respuesta.get('ok')}", flush=True)
    return bool(respuesta.get('ok'))


def cerradas(cuerpo):
    """Posiciones que ya tienen un cierre en el historial."""
    return {d['posicion'] for d in cuerpo['deals'] if d['entrada'] == 'out' and d['tipo'] in ('buy', 'sell')}


def capturar(posiciones):
    """Captura de pantalla REAL del historial del terminal, para que el bot la publique con el aviso de esas
    operaciones. Si falla, no pasa nada: el aviso sale igual, sin imagen."""
    try:
        import captura
        time.sleep(2)  # que el terminal pinte la fila nueva
        nombre = captura.mandar(captura.png_de(captura.historial()), sorted(posiciones))
        print(f'{datetime.now(MADRID):%H:%M:%S} captura del historial enviada ({len(posiciones)} operaciones): {bool(nombre)}', flush=True)
    except Exception as e:
        print(f'{datetime.now(MADRID):%H:%M:%S} sin captura: {type(e).__name__}: {e}', flush=True)


def en_horario(ahora):
    return ahora.weekday() < 5 and ABRE <= (ahora.hour, ahora.minute) < CIERRA


def una(mt5):
    cuerpo = leer_con_historial(mt5)
    if not cuerpo:
        raise SystemExit('MT5 ha conectado pero no ha dado historial: no se envía nada')
    if not enviar(cuerpo, 'lectura suelta'):
        raise SystemExit('el bot no ha aceptado la lectura')


def vigilar(mt5):
    cuerpo = leer_con_historial(mt5)
    if not cuerpo:
        raise SystemExit('MT5 ha conectado pero no ha dado historial')
    enviar(cuerpo, 'arranque')
    if not en_horario(datetime.now(MADRID)):
        print('Fuera del horario de mercado: una lectura y fuera.', flush=True)
        return
    empezo = time.time()
    huella = (len(cuerpo['deals']), cuerpo['deals'][-1]['ticket'], cuerpo['balance'])
    ya_cerradas = cerradas(cuerpo)
    ultimo_envio = time.time()
    fallos = 0
    while True:
        time.sleep(CADA)
        ahora = datetime.now(MADRID)
        if time.time() - empezo > MAX_VIGILANCIA:
            print('Límite de tiempo del trabajo: toma el relevo el siguiente.', flush=True)
            return
        cuerpo = leer(mt5)
        if not cuerpo or not cuerpo['deals']:
            fallos += 1
            print(f'{ahora:%H:%M:%S} MT5 no contesta ({fallos})', flush=True)
            if fallos >= 3:
                mt5.shutdown()
                if not conectar(mt5):
                    raise SystemExit('MT5 se ha desconectado y no vuelve')
                fallos = 0
            continue
        fallos = 0
        nueva = (len(cuerpo['deals']), cuerpo['deals'][-1]['ticket'], cuerpo['balance'])
        if not en_horario(ahora):
            # Acaba de cerrar el mercado: la lectura del día, ya con todo cerrado, y fin de la vigilancia.
            for _ in range(5):
                if enviar(cuerpo, 'cierre del día'):
                    return
                time.sleep(15)
            raise SystemExit('no se pudo enviar la lectura del cierre')
        if nueva != huella:
            # Primero la captura de lo que se acaba de cerrar: así el bot ya la tiene cuando le llegue la lectura.
            recien = cerradas(cuerpo) - ya_cerradas
            if recien:
                capturar(recien)
                ya_cerradas |= recien
            if enviar(cuerpo, 'cambio en la cuenta'):
                huella, ultimo_envio = nueva, time.time()
        elif time.time() - ultimo_envio >= LATIDO:
            if enviar(cuerpo, 'sigo aquí'):
                ultimo_envio = time.time()


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else 'una'
    import MetaTrader5 as mt5
    if not conectar(mt5):
        raise SystemExit('MT5 no conecta')
    try:
        (vigilar if modo == 'vigilar' else una)(mt5)
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
