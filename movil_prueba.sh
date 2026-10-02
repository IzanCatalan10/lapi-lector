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
adb shell getprop ro.product.cpu.abilist
unzip -l mt5.apk | grep -o "lib/[^/]*/" | sort -u | tr "
" " "; echo
adb install -r -g mt5.apk || { echo 'no se pudo instalar'; exit 1; }
adb shell pm list packages | grep -i metaquotes
captura "inicio-del-movil"
adb shell am start -n net.metaquotes.metatrader5/.ui.MainActivity 2>&1 | tail -2
adb shell monkey -p net.metaquotes.metatrader5 -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
for espera in 45 60; do
  sleep $espera
  echo "== tras $espera s mas"
  echo "proceso: $(adb shell pidof net.metaquotes.metatrader5)"
  adb shell dumpsys activity activities | grep -E 'mResumedActivity|topResumedActivity' | sed -E 's/[0-9]{5,}/#/g' | head -3
  adb shell dumpsys window | grep -E 'mCurrentFocus' | sed -E 's/[0-9]{5,}/#/g'
  captura "paso-$espera"
  textos
done
echo "== registro de la app"
adb logcat -d 2>/dev/null | grep -i -E 'FATAL|AndroidRuntime|ANR in|metaquotes.*(error|exception|crash)|UnsatisfiedLink|SIGSEGV|libndk' | sed -E 's/[0-9]{5,}/#/g' | tail -25
