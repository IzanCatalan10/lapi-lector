#!/usr/bin/env bash
# Prueba: instala la app oficial de MetaTrader 5 en el móvil virtual, la abre y manda al bot una captura de lo que se ve.
set -u

captura() { # captura "etiqueta": manda la pantalla al bot y enseña el nombre con el que queda guardada
  adb exec-out screencap -p > pantalla.png
  nombre=$(curl -s -X POST -H "authorization: Bearer $INGESTA_CLAVE" -H 'content-type: image/png' --data-binary @pantalla.png "${BOT_URL%/}/captura" | sed 's/.*\/img\///; s/".*//')
  echo "captura $1: $nombre"
}
textos() { # lo que hay escrito en pantalla (sin números largos: nada de cuentas en un registro público)
  adb shell uiautomator dump /sdcard/v.xml >/dev/null 2>&1
  adb shell cat /sdcard/v.xml | grep -o 'text="[^"]*"\|resource-id="[^"]*"\|bounds="[^"]*"' | paste - - - 2>/dev/null | grep -v 'text=""' | sed -E 's/[0-9]{5,}/#/g' | head -60
}

# El instalador oficial, el que enlaza metatrader5.com en "Download APK".
curl -sL -o mt5.apk 'https://download.terminal.free/cdn/web/metaquotes.software.corp/mt5/metatrader5.apk'
ls -la mt5.apk
file mt5.apk | cut -c1-120
adb install -r -g mt5.apk || { echo 'no se pudo instalar'; exit 1; }
adb shell pm list packages | grep -i metaquotes
adb shell monkey -p net.metaquotes.metatrader5 -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 25
captura arranque
textos
