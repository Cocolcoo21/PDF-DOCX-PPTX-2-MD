"""Inventario recursivo de PDFs: páginas, tipo (nativo/escaneado), imágenes embebidas.

Uso:
    python inventario.py [directorio]   # por defecto, el directorio actual
"""
import csv
import sys
from pathlib import Path

import fitz  # PyMuPDF


def classify_page(page):
    text = page.get_text("text").strip()
    images = page.get_images(full=True)
    return len(text), len(images)


def analyze_pdf(path: Path, root: Path):
    doc = fitz.open(path)
    n_pages = len(doc)
    pages_with_text = 0
    embedded_images_seen = set()

    for page in doc:
        text_len, _ = classify_page(page)
        if text_len > 30:
            pages_with_text += 1
        for img in page.get_images(full=True):
            embedded_images_seen.add(img[0])  # xref, dedup shared images

    doc.close()

    text_ratio = pages_with_text / n_pages if n_pages else 0
    tipo = "nativo" if text_ratio >= 0.6 else "escaneado"

    return {
        "ruta": str(path.relative_to(root)),
        "paginas": n_pages,
        "tipo": tipo,
        "paginas_con_texto": pages_with_text,
        "ratio_texto": round(text_ratio, 2),
        "imagenes_embebidas": len(embedded_images_seen),
        "tam_mb": round(path.stat().st_size / (1024 * 1024), 2),
    }


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    pdfs = sorted(root.rglob("*.pdf"))
    rows = []
    for pdf in pdfs:
        try:
            rows.append(analyze_pdf(pdf, root))
        except Exception as e:
            rows.append({
                "ruta": str(pdf.relative_to(root)),
                "paginas": "ERROR",
                "tipo": "ERROR",
                "paginas_con_texto": "",
                "ratio_texto": "",
                "imagenes_embebidas": "",
                "tam_mb": round(pdf.stat().st_size / (1024 * 1024), 2),
            })
            print(f"ERROR procesando {pdf}: {e}", file=sys.stderr)

    out_path = root / "inventario.csv"
    fieldnames = ["ruta", "paginas", "tipo", "paginas_con_texto", "ratio_texto", "imagenes_embebidas", "tam_mb"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Inventario generado: {out_path} ({len(rows)} PDFs)")
    for r in rows:
        print(f"  {r['ruta']}: {r['paginas']} pag, {r['tipo']}, {r['imagenes_embebidas']} img, {r['tam_mb']} MB")


if __name__ == "__main__":
    main()
