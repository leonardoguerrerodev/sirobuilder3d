#!/usr/bin/env bash
# SiroBuilder - Fase 1 del fantasma, todo de corrido (v2).
#
#   1. Saca el codigo VIEJO del commit 702c029 a una carpeta temporal (no toca tu
#      arbol) y lo mide con la auto-ejecucion de scripts DESACTIVADA de verdad
#      (--factory-startup --disable-autoexec: ignora tus preferencias y tus
#      extensiones instaladas).
#   2. Si tu arbol todavia es el viejo, aplica fase1-fantasma-sin-drivers.patch.
#      Si ya tiene el parche, lo deja como esta.
#   3. Mide el codigo NUEVO (el de tu arbol) igual.
#
# Uso, desde la raiz del repo (la carpeta que contiene sirobuilder/):
#     bash correr_todo.sh
#
# Deja todo en resultado_fase1.txt. Hace un respaldo fechado en
# respaldo_siro_<fecha>/ antes de tocar nada. No hace commit.

cd "$(dirname "$0")" || exit 1

main() {
  echo "### 0. Comprobaciones previas"
  for f in sirobuilder/operators/ghost_preview.py diagnostico_fantasma.py; do
    [ -f "$f" ] || { echo "FALTA: $f"; return 1; }
  done
  command -v blender >/dev/null || { echo "No encuentro 'blender' en el PATH"; return 1; }

  if grep -q register_driver_function sirobuilder/operators/ghost_preview.py; then
    ESTADO=viejo
    [ -f fase1-fantasma-sin-drivers.patch ] || { echo "Tu codigo es el viejo y falta fase1-fantasma-sin-drivers.patch"; return 1; }
  else
    ESTADO=nuevo
  fi
  echo "Tu arbol tiene el codigo: $ESTADO"

  B="blender -b --factory-startup --disable-autoexec"
  RESP="respaldo_siro_$(date +%F_%H%M%S)"
  mkdir -p "$RESP/viejo" || return 1
  cp -r sirobuilder "$RESP/sirobuilder"
  [ -f tests/test_ghost_fase1.py ] && cp tests/test_ghost_fase1.py "$RESP/test_ghost_fase1.orig.py"
  echo "Respaldo en $RESP"

  # --- codigo viejo, sacado de git ---
  VIEJO_OK=1
  if ! git cat-file -e 702c029 2>/dev/null; then git fetch -q origin 2>/dev/null; fi
  if git archive 702c029 sirobuilder 2>/dev/null | tar -x -C "$RESP/viejo" && [ -f "$RESP/viejo/sirobuilder/operators/ghost_preview.py" ]; then
    RAIZ_VIEJO="$PWD/$RESP/viejo"
    echo "Codigo viejo extraido de 702c029 en $RAIZ_VIEJO"
  else
    VIEJO_OK=0
    echo "No pude sacar 702c029 de git: me salto las corridas del codigo viejo."
  fi

  # --- aplicar el parche si hace falta ---
  if [ "$ESTADO" = viejo ]; then
    [ -f tests/test_ghost_fase1.py ] && rm tests/test_ghost_fase1.py  # el parche trae el suyo
    if ! git apply --check fase1-fantasma-sin-drivers.patch 2> "$RESP/apply_check.err"; then
      echo "El parche NO aplica limpio (cambios locales en los mismos archivos?):"
      cat "$RESP/apply_check.err"
      [ -f "$RESP/test_ghost_fase1.orig.py" ] && cp "$RESP/test_ghost_fase1.orig.py" tests/test_ghost_fase1.py
      echo "No se toco nada del codigo."
      return 1
    fi
    git apply fase1-fantasma-sin-drivers.patch || return 1
    echo "Parche aplicado (sin commit)."
  fi
  [ -f tests/test_ghost_fase1.py ] || { echo "Falta tests/test_ghost_fase1.py"; return 1; }

  # correccion del caso 0 contra 0 (pieza desplazada +1 en Z): el plano roza el
  # fondo de la esfera y lo correcto es 0 caras fantasma, igual que el oraculo
  cp tests/test_ghost_fase1.py "$RESP/test_ghost_fase1.antes.py"
  sed -i 's/check(nombre, n > 0 and cerca(f, esp),/check(nombre, (n > 0 or esp == 0) and cerca(f, esp),/' tests/test_ghost_fase1.py
  grep -q 'n > 0 or esp == 0' tests/test_ghost_fase1.py || echo "AVISO: no pude aplicar la correccion 0 contra 0 al test"

  if [ "$VIEJO_OK" = 1 ]; then
    echo
    echo "### 1. Diagnostico del codigo VIEJO (auto-ejecucion OFF)"
    SIRO_REPO="$RAIZ_VIEJO" $B --python diagnostico_fantasma.py 2>&1 | tee "$RESP/1_diag_viejo.log"

    echo
    echo "### 2. Test de la Fase 1 contra el codigo VIEJO (debe FALLAR en drivers y flecha)"
    SIRO_REPO="$RAIZ_VIEJO" $B --python tests/test_ghost_fase1.py 2>&1 | tee "$RESP/2_test_viejo.log"
    R_VIEJO=${PIPESTATUS[0]}
  fi

  echo
  echo "### 3. Test de la Fase 1 contra el codigo NUEVO (el de tu arbol; debe dar TODO OK)"
  SIRO_REPO="$PWD" $B --python tests/test_ghost_fase1.py 2>&1 | tee "$RESP/3_test_nuevo.log"
  R_NUEVO=${PIPESTATUS[0]}

  echo
  echo "################ RESUMEN ################"
  if [ "$VIEJO_OK" = 1 ]; then
    echo "--- Diagnostico viejo, auto-ejecucion OFF:"
    grep -E "Auto Run|fantasma [0-9]+/|drivers validos|EXCEPCION" "$RESP/1_diag_viejo.log"
    echo
    echo "--- Test contra codigo VIEJO (codigo de salida $R_VIEJO, se espera 1):"
    grep -E "Auto Run|FALLA|FALLARON|TODO OK" "$RESP/2_test_viejo.log"
    echo
  fi
  echo "--- Test contra codigo NUEVO (codigo de salida $R_NUEVO, se espera 0):"
  grep -E "Auto Run|FALLA|FALLARON|TODO OK" "$RESP/3_test_nuevo.log"
  echo
  echo "Revisar: git status && git diff --stat"
  if [ "$ESTADO" = viejo ]; then
    echo "Deshacer el parche: git checkout -- sirobuilder README.md"
  fi
}

main 2>&1 | tee resultado_fase1.txt
