#!/bin/sh
# Batería completa en dos pasos (comando por omisión del servicio «pruebas»):
#   1. las rápidas (sin navegador) en paralelo con pytest-xdist;
#   2. los recorridos de navegador (Playwright), con menos procesos porque cada uno abre su Chromium.
# Variables: PRUEBAS_N (procesos de las rápidas, 4 por omisión), PRUEBAS_N_NAVEGADOR (procesos de los recorridos);
# con 0 corre en serie. PDF_REAL=1 y CAPTURAS=1 se heredan.
N="${PRUEBAS_N:-4}"
NN="${PRUEBAS_N_NAVEGADOR:-3}"
pytest -m "not navegador" -n "$N" -q
r1=$?
pytest -m navegador -n "$NN" -q
r2=$?
[ "$r1" -eq 0 ] && [ "$r2" -eq 0 ]
