"""Genera descripciones (captions) para todas las imágenes extraídas en
output/, usando la API de Claude en paralelo, e inserta cada descripción
como texto justo debajo de la imagen en su .md correspondiente.

Por qué archivos separados y no base64: el costo en tokens de un modelo de
visión depende de la RESOLUCIÓN de la imagen, no del encoding (Claude
tokeniza en parches de 28x28px). Base64 no ahorra nada y solo infla el
.md / ensucia los diffs de git. El captioning es lo que hace que el
contenido de diagramas/mapas sea buscable por texto (RAG puro-texto no
puede "ver" una imagen sin esto).

Requiere ANTHROPIC_API_KEY en el entorno o en un .env en este directorio
(no la pegues en el chat de un agente — configúrala tú mismo).

Uso:
    python caption_imagenes.py                 # todas las imágenes de output/
    python caption_imagenes.py --dry-run        # solo cuenta, no llama a la API
    python caption_imagenes.py --limit 3         # smoke test antes de correr todo
    python caption_imagenes.py --from-file f.txt # solo las imágenes listadas (una ruta por línea)
"""
import argparse
import base64
import concurrent.futures
import os
import re
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path.cwd()
OUTPUT = ROOT / "output"
MODEL = "claude-sonnet-4-5"  # cambiar a un Haiku si el costo importa más que la calidad
MAX_WORKERS = 10
IMG_EXTS = {".png", ".jpg", ".jpeg"}

PROMPT = (
    "Describe brevemente el contenido de esta imagen en español, en 1-2 "
    "frases. Es una imagen extraída de un documento (informe, manual o "
    "artículo). Si es un diagrama, mapa o esquema técnico, describe qué "
    "representa (elementos clave, relaciones, términos visibles). Si es "
    "solo un logo, decoración o foto genérica sin contenido informativo "
    "relevante, dilo brevemente. No agregues preámbulo, responde solo con "
    "la descripción."
)


def media_type_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}[ext.lstrip(".")]


def caption_image(client, img_path: Path) -> str:
    data = base64.standard_b64encode(img_path.read_bytes()).decode("utf-8")
    resp = client.messages.create(
        model=MODEL,
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type_for(img_path), "data": data}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    return resp.content[0].text.strip()


def find_md_files_referencing(img_path: Path) -> list[Path]:
    """Un .md por carpeta de documento; la imagen vive en la misma carpeta o en assets/."""
    doc_dir = img_path.parent if img_path.parent.name != "assets" else img_path.parent.parent
    return list(doc_dir.glob("*.md"))


_md_locks: dict[Path, threading.Lock] = {}
_md_locks_guard = threading.Lock()


def _lock_for(md_path: Path) -> threading.Lock:
    # Varias imágenes de un mismo documento se procesan en paralelo, pero
    # todas hacen read-modify-write del MISMO .md. Sin un lock por archivo,
    # dos hilos pueden leer la misma versión y el segundo write pisa el
    # primero (lost update) -> captions que desaparecen silenciosamente.
    with _md_locks_guard:
        if md_path not in _md_locks:
            _md_locks[md_path] = threading.Lock()
        return _md_locks[md_path]


def insert_caption(md_path: Path, img_name: str, caption: str) -> bool:
    # Solo inserta en la PRIMERA aparición de esa imagen en el documento. Si
    # Marker duplicó una página (mismo nombre de imagen referenciado dos
    # veces), la segunda aparición se queda sin caption — revisar con
    # dedup_captions.py / auditar manualmente si el conteo final no cuadra.
    pattern = re.compile(r'(!\[[^\]]*\]\([^)]*' + re.escape(img_name) + r'\))')
    marker = f"\n\n*[descripción generada por IA: {caption}]*"
    with _lock_for(md_path):
        text = md_path.read_text(encoding="utf-8")
        new_text, n = pattern.subn(lambda m: m.group(1) + marker, text, count=1)
        if n:
            md_path.write_text(new_text, encoding="utf-8")
    return n > 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--from-file", type=str, default=None,
                         help="Archivo con una ruta de imagen por línea, en vez de escanear output/")
    args = parser.parse_args()

    if args.from_file:
        images = [Path(line.strip()) for line in Path(args.from_file).read_text().splitlines() if line.strip()]
    else:
        images = sorted(p for p in OUTPUT.rglob("*") if p.suffix.lower() in IMG_EXTS)
    if args.limit:
        images = images[:args.limit]
    print(f"Imágenes encontradas: {len(images)}")

    if args.dry_run:
        print("Dry run, no se llama a la API.")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: falta ANTHROPIC_API_KEY (env var o .env)", file=sys.stderr)
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic()

    done = 0
    errors = 0
    lock = threading.Lock()

    def process(img_path: Path):
        nonlocal done, errors
        try:
            caption = caption_image(client, img_path)
            mds = find_md_files_referencing(img_path)
            inserted = False
            for md in mds:
                if insert_caption(md, img_path.name, caption):
                    inserted = True
            with lock:
                done += 1
                status = "OK" if inserted else "OK (sin referencia en .md)"
                print(f"[{done}/{len(images)}] {status}: {img_path.name} -> {caption[:80]}")
        except Exception as e:
            with lock:
                errors += 1
                print(f"[ERROR] {img_path}: {e}", file=sys.stderr)

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        list(ex.map(process, images))

    elapsed = time.time() - start
    print(f"\nCompletado en {elapsed/60:.1f} min. OK: {done - errors} | Errores: {errors}")


if __name__ == "__main__":
    main()
