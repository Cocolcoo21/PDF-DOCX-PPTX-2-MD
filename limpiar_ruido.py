"""Elimina imágenes de ruido (logos de encabezado, marcas de agua, sellos
repetidos) de un documento ya convertido, y quita sus enlaces del .md.

Motivación: los manuales institucionales repiten un logo en el encabezado de
CADA página y suelen llevar una marca de agua diagonal. Tanto pymupdf4llm como
Marker las extraen como imágenes reales, así que un manual de 74 páginas puede
terminar con ~110 imágenes de las que solo 5 son figuras de contenido. Eso
ensucia el markdown, infla la carpeta y —lo más caro— multiplica por 20 el
costo del paso de captioning (caption_imagenes.py), que describiría 60 veces
el mismo escudo.

Heurística (dos señales independientes, ambas conservadoras):

1. Imágenes DUPLICADAS: mismo hash MD5 en más de un archivo. Una figura de
   contenido no se repite; un logo de encabezado sí, decenas de veces.
2. Imágenes MINÚSCULAS: por debajo de --min-kb (default 5KB). Los logos y
   viñetas pesan 1-3KB; cualquier diagrama, tabla-como-imagen o foto pesa
   decenas o cientos de KB.

Lo que NO hace: no intenta decidir por contenido semántico (eso es trabajo del
modelo de visión en caption_imagenes.py). Ante la duda, conserva.

Uso:
    python limpiar_ruido.py output/docs/MI_DOCUMENTO          # ver qué haría
    python limpiar_ruido.py output/docs/MI_DOCUMENTO --apply  # aplicar
    python limpiar_ruido.py output/ --recursive --apply       # todo el lote

Sin --apply es un dry-run: lista lo que borraría y no toca nada.
"""
import argparse
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")


def find_doc_dirs(root: Path, recursive: bool):
    """Carpetas de documento = las que contienen al menos un .md."""
    if not recursive:
        return [root]
    return sorted({p.parent for p in root.rglob("*.md")})


def collect_images(doc_dir: Path):
    """Imágenes del documento, tanto planas (Marker) como en assets/ (pymupdf4llm)."""
    imgs = [p for p in doc_dir.iterdir() if p.suffix.lower() in IMG_EXT]
    assets = doc_dir / "assets"
    if assets.is_dir():
        imgs += [p for p in assets.iterdir() if p.suffix.lower() in IMG_EXT]
    return sorted(imgs)


def classify(images, min_kb: float):
    """Devuelve (ruido, conservadas) según duplicado-por-hash o tamaño mínimo."""
    by_hash = defaultdict(list)
    for p in images:
        by_hash[hashlib.md5(p.read_bytes()).hexdigest()].append(p)

    ruido, conservadas = [], []
    for grupo in by_hash.values():
        duplicada = len(grupo) > 1
        for p in grupo:
            minuscula = p.stat().st_size < min_kb * 1024
            if duplicada or minuscula:
                motivo = "duplicada" if duplicada else "minúscula"
                if duplicada and minuscula:
                    motivo = "duplicada+minúscula"
                ruido.append((p, motivo, len(grupo)))
            else:
                conservadas.append(p)
    return sorted(ruido, key=lambda r: -r[2]), sorted(conservadas)


def strip_links(md_text: str, nombres: set, doc_dir: Path) -> tuple[str, int]:
    """Quita enlaces de imagen ![...](ruta) que sobran, y las líneas que quedan vacías.

    Borra tres casos, por OCURRENCIA y no por línea completa: Marker a veces
    emite dos imágenes pegadas en la misma línea, así que un filtro de "línea
    que es exactamente una imagen" dejaría enlaces colgando.

    1. ruta cuyo basename está en `nombres` (el ruido que este script borra);
    2. enlace vacío `![]()`, que Marker emite cuando se salta una imagen
       (p. ej. la de área cero del parche fix_marker_empty_image.py);
    3. referencia ROTA: el archivo no existe en la carpeta del documento.
       Esto hace el script idempotente y repara .md de corridas anteriores.

    Una imagen que comparte línea con texto se quita igual, pero la línea se
    conserva: solo se elimina la línea si queda vacía.
    """
    quitadas = 0
    patron = re.compile(r"!\[[^\]]*\]\(([^)]*)\)")

    def sobra(ruta: str) -> bool:
        if not ruta.strip():
            return True
        nombre = Path(ruta).name
        if nombre in nombres:
            return True
        return not (doc_dir / ruta).exists()

    salida = []
    for linea in md_text.splitlines():
        if "![" in linea:
            nueva = patron.sub(lambda m: "" if sobra(m.group(1)) else m.group(0), linea)
            quitadas += len(patron.findall(linea)) - len(patron.findall(nueva))
            if not nueva.strip() and linea.strip():
                continue  # la línea era solo imágenes: se va entera
            linea = nueva
        salida.append(linea)

    texto = "\n".join(salida)
    # Colapsa los huecos de 3+ líneas en blanco que deja el borrado.
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto, quitadas


def procesar(doc_dir: Path, min_kb: float, apply: bool) -> bool:
    images = collect_images(doc_dir)
    mds = sorted(doc_dir.glob("*.md"))
    if not images:
        return False

    ruido, conservadas = classify(images, min_kb)
    print(f"\n{doc_dir}")
    print(f"  {len(images)} imágenes: {len(ruido)} de ruido, {len(conservadas)} conservadas")
    for p in conservadas:
        print(f"    conservar  {p.stat().st_size // 1024:5d}KB  {p.name}")
    vistos = set()
    for p, motivo, n in ruido:
        if motivo not in vistos or n > 1:
            vistos.add(motivo)
    print(f"    borrar     {len(ruido)} archivos ({sum(p.stat().st_size for p, _, _ in ruido) // 1024}KB)")

    if not apply:
        print("  [dry-run] nada modificado; usar --apply para aplicar.")
        return False

    nombres = {p.name for p, _, _ in ruido}
    for p, _, _ in ruido:
        p.unlink()
    # Los enlaces se limpian DESPUÉS de borrar, para que la detección de
    # referencias rotas de strip_links() vea el estado final de la carpeta.
    for md in mds:
        texto = md.read_text(encoding="utf-8")
        nuevo, quitadas = strip_links(texto, nombres, doc_dir)
        if quitadas:
            md.write_text(nuevo, encoding="utf-8")
            print(f"  {md.name}: {quitadas} enlaces de imagen quitados")
    print(f"  {len(ruido)} archivos borrados")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", help="carpeta del documento (o raíz, con --recursive)")
    ap.add_argument("--apply", action="store_true", help="aplicar los cambios (por defecto, dry-run)")
    ap.add_argument("--recursive", action="store_true", help="procesar todas las carpetas con .md bajo la ruta dada")
    ap.add_argument("--min-kb", type=float, default=5.0, help="tamaño bajo el cual una imagen se considera ruido (default: 5)")
    args = ap.parse_args()

    root = Path(args.carpeta)
    if not root.is_dir():
        print(f"No es una carpeta: {root}", file=sys.stderr)
        sys.exit(1)

    for doc_dir in find_doc_dirs(root, args.recursive):
        procesar(doc_dir, args.min_kb, args.apply)


if __name__ == "__main__":
    main()
