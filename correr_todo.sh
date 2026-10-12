#!/usr/bin/env bash
# SiroBuilder - Fase 1 del fantasma, todo de corrido.
#
#   1. Mide el codigo VIEJO con la auto-ejecucion de scripts DESACTIVADA de verdad
#      (--factory-startup + --disable-autoexec: ignora tus preferencias y tus
#      extensiones instaladas).
#   2. Aplica fase1-fantasma-sin-drivers.patch.
#   3. Mide el codigo NUEVO igual.
#
# Uso, desde la raiz del repo (la carpeta que contiene sirobuilder/):
#     bash correr_todo.sh
#
# Deja todo en resultado_fase1.txt. Antes de tocar nada hace un respaldo fechado
# en respaldo_siro_<fecha>/. No hace commit.

cd "$(dirname "$0")" || exit 1

main() {
  echo "### 0. Comprobaciones previas"
  for f in sirobuilder/operators/ghost_preview.py fase1-fantasma-sin-drivers.patch \
           tests/test_ghost_fase1.py diagnostico_fantasma.py; do
    [ -f "$f" ] || { echo "FALTA: $f"; return 1; }
  done
  command -v blender >/dev/null || { echo "No encuentro 'blender' en el PATH"; return 1; }
  grep -q register_driver_function sirobuilder/operators/ghost_preview.py || {
    echo "El codigo ya no es el viejo (no tiene register_driver_function): el parche parece aplicado."
    return 1
  }
  grep -q 'n > 0 and cerca(f, esp),' tests/test_ghost_fase1.py || {
    echo "tests/test_ghost_fase1.py no es la version que esperaba (la del oraculo)."
    return 1
  }

  B="blender -b --factory-startup --disable-autoexec"
  export SIRO_REPO="$PWD"
  RESP="respaldo_siro_$(date +%F_%H%M%S)"
  mkdir -p "$RESP" || return 1
  cp -r sirobuilder "$RESP/sirobuilder"
  cp tests/test_ghost_fase1.py "$RESP/test_ghost_fase1.orig.py"

  # correccion del caso 0 contra 0: con la pieza desplazada +1 en Z el plano roza
  # el fondo de la esfera y lo correcto es 0 caras fantasma (el oraculo tambien da 0)
  FIX="$RESP/test_ghost_fase1.fix.py"
  sed 's/check(nombre, n > 0 and cerca(f, esp),/check(nombre, (n > 0 or esp == 0) and cerca(f, esp),/' \
      "$RESP/test_ghost_fase1.orig.py" > "$FIX"
  grep -q 'n > 0 or esp == 0' "$FIX" || { echo "No pude corregir el test"; return 1; }
  echo "Respaldo en $RESP"

  echo
  echo "### 1. Diagnostico del codigo VIEJO (auto-ejecucion OFF)"
  $B --python diagnostico_fantasma.py 2>&1 | tee "$RESP/1_diag_viejo.log"

  echo
  echo "### 2. Test de la Fase 1 contra el codigo VIEJO (debe FALLAR en drivers y flecha)"
  $B --python "$FIX" 2>&1 | tee "$RESP/2_test_viejo.log"
  R_VIEJO=${PIPESTATUS[0]}

  echo
  echo "### 3. Aplicar el parche"
  rm tests/test_ghost_fase1.py   # el parche trae su propio tests/test_ghost_fase1.py
  if ! git apply --check fase1-fantasma-sin-drivers.patch 2> "$RESP/apply_check.err"; then
    echo "El parche NO aplica limpio (cambios locales en los mismos archivos?):"
    cat "$RESP/apply_check.err"
    cp "$RESP/test_ghost_fase1.orig.py" tests/test_ghost_fase1.py
    echo "No se toco nada del codigo. Respaldo en $RESP"
    return 1
  fi
  git apply fase1-fantasma-sin-drivers.patch || return 1
  cp "$FIX" tests/test_ghost_fase1.py
  echo "Parche aplicado (sin commit)."

  echo
  echo "### 4. Test de la Fase 1 contra el codigo NUEVO (debe dar TODO OK)"
  $B --python tests/test_ghost_fase1.py 2>&1 | tee "$RESP/3_test_nuevo.log"
  R_NUEVO=${PIPESTATUS[0]}

  echo
  echo "################ RESUMEN ################"
  echo "--- Diagnostico viejo, auto-ejecucion OFF:"
  grep -E "Auto Run|fantasma [0-9]+/|drivers validos|EXCEPCION" "$RESP/1_diag_viejo.log"
  echo
  echo "--- Test contra codigo VIEJO (codigo de salida $R_VIEJO, se espera 1):"
  grep -E "Auto Run|FALLA|FALLARON|TODO OK" "$RESP/2_test_viejo.log"
  echo
  echo "--- Test contra codigo NUEVO (codigo de salida $R_NUEVO, se espera 0):"
  grep -E "Auto Run|FALLA|FALLARON|TODO OK" "$RESP/3_test_nuevo.log"
  echo
  echo "Revisar:  git status && git diff --stat"
  echo "Deshacer: git checkout -- sirobuilder README.md && cp $RESP/test_ghost_fase1.orig.py tests/test_ghost_fase1.py"
}

main 2>&1 | tee resultado_fase1.txt
