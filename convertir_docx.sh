#!/bin/bash
# Convierte DOCX a Markdown con pandoc, extrayendo imágenes embebidas.
# Requiere: brew install pandoc (o el gestor de paquetes de tu SO).
#
# Uso:
#   ./convertir_docx.sh "carpeta/documento.docx" ["otro.docx" ...]
#
# Salida: output/<carpeta-saneada>/<documento-saneado>/<documento>.md
# con imágenes en .../media/ (nombre por defecto de pandoc).
#
# Nota: pandoc solo extrae imágenes que estén referenciadas en el cuerpo del
# documento (no las de encabezados/pies de página). Si extract-media saca
# imágenes que no aparecen enlazadas en el .md, son decorativas y se pueden
# ignorar o eliminar manualmente.

set -uo pipefail

if [ "$#" -eq 0 ]; then
  echo "Uso: $0 archivo1.docx [archivo2.docx ...]" >&2
  exit 1
fi

slugify() {
  echo "$1" | sed 's/[()]/-/g; s/ /_/g'
}

for docx in "$@"; do
  base=$(basename "$docx" .docx)
  parent=$(dirname "$docx")
  slug_parent=$(slugify "$parent")
  slug=$(slugify "$base")
  out_dir="output/$slug_parent/$slug"
  mkdir -p "$out_dir"
  echo "Convirtiendo: $base"
  if pandoc "$docx" -f docx -t gfm --extract-media="$out_dir" -o "$out_dir/$base.md"; then
    echo "  OK -> $out_dir/$base.md"
  else
    echo "  ERROR convirtiendo $base" >&2
  fi
done
