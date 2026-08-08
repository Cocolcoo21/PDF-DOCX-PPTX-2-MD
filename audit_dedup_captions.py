"""Audita y limpia los captions generados por caption_imagenes.py:

- `--audit`: lista imágenes referenciadas en output/ que no tienen un
  caption inmediatamente debajo (guarda además missing_captions.txt para
  reprocesar con `caption_imagenes.py --from-file missing_captions.txt`).
- `--dedup`: elimina captions duplicados consecutivos (mismo bloque de
  imagen con 2+ descripciones seguidas, típicamente por reintentos sobre
  imágenes que ya tenían caption), dejando solo la primera.

Uso:
    python audit_dedup_captions.py --audit
    python audit_dedup_captions.py --dedup
"""
import argparse
import re
from pathlib import Path

ROOT = Path.cwd()
OUTPUT = ROOT / "output"
IMG_RE = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
MARKER = "*[descripción generada por IA:"


def audit():
    missing = []
    for md in sorted(OUTPUT.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        paras = text.split("\n\n")
        for i, p in enumerate(paras):
            m = IMG_RE.search(p)
            if not m:
                continue
            ref = m.group(1)
            if ref.startswith("http"):
                continue
            img_path = (md.parent / ref).resolve()
            if not img_path.exists():
                continue
            has_caption_next = i + 1 < len(paras) and paras[i + 1].startswith(MARKER)
            if not has_caption_next:
                missing.append(str(img_path))

    print(f"Imágenes sin caption: {len(missing)}")
    for m in missing:
        print(f"  {m}")
    if missing:
        (ROOT / "missing_captions.txt").write_text("\n".join(missing))
        print(f"\nGuardado en missing_captions.txt — reprocesar con:\n"
              f"  python caption_imagenes.py --from-file missing_captions.txt")
    print(
        "\nNota: si un .md tiene el mismo nombre de imagen referenciado dos "
        "veces (Marker a veces duplica una página completa), la segunda "
        "aparición queda sin caption aunque la imagen sí esté descrita — "
        "es contenido redundante, no información perdida. Revisar con:\n"
        "  grep -c 'IMG_NAME' archivo.md"
    )


def dedup():
    total_removed = 0
    files_changed = 0
    for md in sorted(OUTPUT.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        if MARKER not in text:
            continue
        paras = text.split("\n\n")
        out = []
        removed = 0
        i = 0
        while i < len(paras):
            out.append(paras[i])
            if paras[i].startswith(MARKER):
                j = i + 1
                while j < len(paras) and paras[j].startswith(MARKER):
                    removed += 1
                    j += 1
                i = j
            else:
                i += 1
        if removed:
            md.write_text("\n\n".join(out), encoding="utf-8")
            files_changed += 1
            total_removed += removed
            print(f"{md.relative_to(ROOT)}: -{removed} duplicados")
    print(f"\nTotal: {total_removed} captions duplicados eliminados en {files_changed} archivos")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--audit", action="store_true")
    group.add_argument("--dedup", action="store_true")
    args = parser.parse_args()

    if args.audit:
        audit()
    else:
        dedup()
