#!/bin/bash
# Convierte PDFs a Markdown con Marker (modo balanced: VLM layout + OCR completo).
# Más lento que pymupdf4llm pero resuelve mucho mejor layouts multicolumna
# complejos y jerarquía de encabezados en documentos densos (ver README.md).
#
# Requiere: pip install marker-pdf, y en Mac sin GPU NVIDIA: brew install llama.cpp
# (el modo balanced usa Metal/GPU de Apple Silicon automáticamente vía llama-server).
#
# IMPORTANTE: aplicar antes patches/fix_surya_grammar.py (ver README.md) o la
# conversión puede fallar/degradarse por un bug conocido de surya-ocr.
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

for pdf in "$@"; do
  base=$(basename "$pdf" .pdf)
  parent=$(dirname "$pdf")
  slug_parent=$(slugify "$parent")
  slug=$(slugify "$base")
  out_dir="$OUT_ROOT/$slug_parent/$slug"
  echo "=== $(date '+%H:%M:%S') Convirtiendo: $base ===" | tee -a "$LOG"
  start=$(date +%s)
  if marker_single "$pdf" --mode balanced --output_dir "$out_dir" >> "$LOG" 2>&1; then
    end=$(date +%s)
    echo "=== $(date '+%H:%M:%S') OK ($((end-start))s): $base ===" | tee -a "$LOG"
  else
    end=$(date +%s)
    echo "=== $(date '+%H:%M:%S') ERROR ($((end-start))s): $base ===" | tee -a "$LOG"
  fi
done

echo "=== $(date '+%H:%M:%S') LOTE COMPLETO ===" | tee -a "$LOG"
