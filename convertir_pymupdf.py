"""Convierte PDFs nativos a Markdown con pymupdf4llm, extrayendo imágenes a assets/.

Rápido y sin GPU. Ideal para PDFs de producción digital con layout simple
(una columna, tablas simples). Para layouts multicolumna complejos, usar
convertir_marker.py en su lugar.

Uso (ejecutar desde el directorio que contiene los PDFs, o pasar rutas
relativas/absolutas a cada PDF):
    python convertir_pymupdf.py "carpeta/documento.pdf" ["otro.pdf" ...]

Salida: output/<misma estructura de carpetas>/<documento>/<documento>.md
        con imágenes en .../assets/imagen.png y enlaces relativos.
"""
import sys
from pathlib import Path

import pymupdf4llm

ROOT = Path.cwd()
OUTPUT = ROOT / "output"


def slugify(name: str) -> str:
    # pymupdf4llm sanea (espacios/paréntesis -> _/-) la ruta que usa para el
    # pix.save() real, pero solo después de haber hecho mkdir con la ruta sin
    # sanear. Si el nombre de carpeta tiene espacios/paréntesis, ambas rutas
    # divergen y el guardado de imágenes falla. Se sanea aquí para que coincidan.
    name = name.replace("(", "-").replace(")", "-").replace(" ", "_")
    return name


def convert_pdf(pdf_path: Path):
    rel = pdf_path.resolve().relative_to(ROOT)
    doc_name = pdf_path.stem
    out_dir = OUTPUT / slugify(str(rel.parent)) / slugify(doc_name)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    md_text = pymupdf4llm.to_markdown(
        str(pdf_path),
        write_images=True,
        image_path=str(assets_dir),
        image_format="png",
        dpi=150,
    )

    # pymupdf4llm embeds image links relative to la CWD (raíz del proyecto),
    # no relativos a la ubicación del propio .md. Se reescriben a "assets/..."
    # para que el markdown sea portable si se mueve output/ o se abre solo.
    out_dir_rel = out_dir.relative_to(ROOT).as_posix()
    md_text = md_text.replace(f"{out_dir_rel}/assets/", "assets/")

    md_path = out_dir / f"{doc_name}.md"
    md_path.write_text(md_text, encoding="utf-8")

    n_images = len(list(assets_dir.glob("*")))
    n_headers = sum(1 for line in md_text.splitlines() if line.strip().startswith("#"))
    return {
        "pdf": str(rel),
        "md": str(md_path.relative_to(ROOT)),
        "chars": len(md_text),
        "imagenes_extraidas": n_images,
        "encabezados": n_headers,
    }


def main(paths):
    if not paths:
        print("Uso: python convertir_pymupdf.py archivo1.pdf [archivo2.pdf ...]", file=sys.stderr)
        sys.exit(1)
    for p in paths:
        pdf_path = Path(p)
        print(f"Convirtiendo: {pdf_path.name} ...")
        try:
            r = convert_pdf(pdf_path)
            print(f"  OK -> {r['md']} | {r['chars']} chars | {r['imagenes_extraidas']} img | {r['encabezados']} headers")
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
