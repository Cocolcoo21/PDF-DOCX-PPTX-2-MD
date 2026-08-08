#!/bin/bash
# Convierte PDFs a Markdown con Marker (modo balanced: VLM layout + OCR completo).
# Más lento que pymupdf4llm pero resuelve mucho mejor layouts multicolumna
# complejos y jerarquía de encabezados en documentos densos (ver README.md).
#
# Requiere: pip install marker-pdf, y en Mac sin GPU NVIDIA: brew install llama.cpp
# (el modo balanced usa Metal/GPU de Apple Silicon automáticamente vía llama-server).
#
# IMPORTANTE: aplicar antes patches/fix_surya_grammar.py y
# patches/fix_marker_empty_image.py (ver README.md) o la conversión puede
# fallar/degradarse por bugs conocidos de surya-ocr/marker-pdf.
#
# Uso:
#   ./convertir_marker.sh "carpeta/documento.pdf" ["otro.pdf" ...]
#
# Salida: output/<carpeta-saneada>/<documento-saneado>/ con el .md e imágenes
# (Marker ya usa nombres de imagen relativos y planos dentro de esa carpeta).

set -uo pipefail

if [ "$#" -eq 0 ]; then
  echo "Uso: $0 archivo1.pdf [archivo2.pdf ...]" >&2
  exit 1
fi

OUT_ROOT="output"
LOG="marker_batch.log"
: > "$LOG"

slugify() {
  echo "$1" | sed 's/[()]/-/g; s/ /_/g'
}

# marker_single crea su propia subcarpeta (nombrada con el filename ORIGINAL,
# no el saneado) dentro de --output_dir, dejando el .md un nivel más adentro
# de lo esperado: out_dir/<nombre-original>/<nombre-original>.md. Esto la
# aplana a out_dir/<nombre-original>.md, para que la estructura sea
# consistente con convertir_pymupdf.py y convertir_pptx.py.
flatten_output() {
  local out_dir="$1"
  for sub in "$out_dir"/*/; do
    sub="${sub%/}"
    [ -d "$sub" ] || continue
    local subname
    subname=$(basename "$sub")
    if [ "$subname" != "assets" ] && ls "$sub"/*.md >/dev/null 2>&1; then
      mv "$sub"/* "$out_dir"/
      rmdir "$sub"
    fi
  done
}

for pdf in "$@"; do
  base=$(basename "$pdf" .pdf)
  parent=$(dirname "$pdf")
  slug_parent=$(slugify "$parent")
  slug=$(slugify "$base")
  out_dir="$OUT_ROOT/$slug_parent/$slug"
  echo "=== $(date '+%H:%M:%S') Convirtiendo: $base ===" | tee -a "$LOG"
  start=$(date +%s)
  if marker_single "$pdf" --mode balanced --output_dir "$out_dir" >> "$LOG" 2>&1; then
    flatten_output "$out_dir"
    end=$(date +%s)
    echo "=== $(date '+%H:%M:%S') OK ($((end-start))s): $base ===" | tee -a "$LOG"
  else
    end=$(date +%s)
    echo "=== $(date '+%H:%M:%S') ERROR ($((end-start))s): $base ===" | tee -a "$LOG"
  fi
done

echo "=== $(date '+%H:%M:%S') LOTE COMPLETO ===" | tee -a "$LOG"
