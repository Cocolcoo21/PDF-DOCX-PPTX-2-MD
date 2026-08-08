"""Parche defensivo para un bug de marker-pdf: crashea al guardar imágenes
de tamaño cero.

Bug: algunas cajas de layout se recortan a una región de área cero (bbox
degenerado del modelo de layout). marker/output.py intenta guardar esa
imagen vacía con Pillow, que revienta con:

    ValueError: cannot write empty image as JPEG

Esto aborta la conversión COMPLETA del documento (aunque ya llevara 20+
minutos procesado), sin ningún workaround por CLI. No hay issue/fix
upstream conocido a la fecha.

Fix: en save_output(), saltar imágenes con width==0 o height==0 (con un
aviso), en vez de abortar todo el documento.

Uso (con el venv activado, después de `pip install marker-pdf`):
    python patches/fix_marker_empty_image.py

Es idempotente. Hay que re-ejecutarlo cada vez que se reinstale/actualice
marker-pdf.
"""
import sys
from pathlib import Path

try:
    import marker
except ImportError:
    print("marker-pdf no está instalado en este entorno (pip install marker-pdf).", file=sys.stderr)
    sys.exit(1)

output_path = Path(marker.__file__).parent / "output.py"
if not output_path.exists():
    print(f"No se encontró {output_path}; puede que la estructura del paquete haya cambiado.", file=sys.stderr)
    sys.exit(1)

text = output_path.read_text(encoding="utf-8")
old = (
    "    for img_name, img in images.items():\n"
    "        img = convert_if_not_rgb(img)  # RGBA images can't save as JPG\n"
    "        img.save(os.path.join(output_dir, img_name), settings.OUTPUT_IMAGE_FORMAT)"
)
new = (
    "    for img_name, img in images.items():\n"
    "        if img.width == 0 or img.height == 0:\n"
    "            # Algunas cajas de layout se recortan a área cero; Pillow no\n"
    "            # puede guardar eso como JPEG. Saltar en vez de abortar todo\n"
    "            # el documento.\n"
    "            print(f\"Warning: skipping empty image '{img_name}' (size {img.size})\")\n"
    "            continue\n"
    "        img = convert_if_not_rgb(img)  # RGBA images can't save as JPG\n"
    "        img.save(os.path.join(output_dir, img_name), settings.OUTPUT_IMAGE_FORMAT)"
)

if new in text:
    print("Ya está parcheado, nada que hacer.")
    sys.exit(0)

n = text.count(old)
if n == 0:
    print("No se encontró el patrón esperado; revisar manualmente output.py "
          "(puede que la versión instalada ya lo haya corregido o cambiado).", file=sys.stderr)
    sys.exit(0)

text = text.replace(old, new)
output_path.write_text(text, encoding="utf-8")
print(f"Parche aplicado en {output_path}.")
