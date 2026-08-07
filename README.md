# pdf-a-md

Pipeline para convertir PDFs (y docx/pptx) a Markdown limpio, con imágenes
extraídas y enlazadas con rutas relativas. Pensado para correr con Claude
Code u otro agente con acceso a bash, sobre una carpeta de documentos propia
del usuario (que **no** vive en este repo — ver `.gitignore`).

Dos motores para PDF, con trade-offs distintos:

- **`pymupdf4llm`**: rápido, sin GPU, sin dependencias pesadas. Buen resultado
  en PDFs de una columna con tablas simples. Falla en layouts multicolumna
  complejos: mezcla el texto de columnas paralelas en un solo párrafo.
- **`Marker`** (Datalab, modo `--mode balanced`): usa un modelo de layout +
  OCR completo vía VLM. Resuelve correctamente multicolumna y genera mejor
  jerarquía de encabezados en documentos densos (manuales, doctrina, informes
  largos). Mucho más lento (~5-30 s/página según complejidad de tablas, vs.
  segundos para el documento completo con pymupdf4llm) y requiere más setup.

Regla práctica: probar primero con `pymupdf4llm` en una muestra; si el
documento tiene multicolumna o la jerarquía de encabezados sale mal, usar
Marker para ese subconjunto.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Solo si vas a usar Marker en Mac sin GPU NVIDIA (usa Metal/Apple Silicon
# automáticamente vía llama-server, sin configuración adicional):
brew install llama.cpp

# Solo si vas a convertir .docx:
brew install pandoc

# Aplicar SIEMPRE después de instalar/actualizar marker-pdf, antes de usar
# --mode balanced (ver detalle del bug en patches/fix_surya_grammar.py):
python patches/fix_surya_grammar.py
```

## Fase 0 — Entorno

- Lanzar la sesión con acceso a la carpeta de documentos (ej. `claude --add-dir /ruta/a/documentos`).
- Verificar salida a internet para instalar paquetes de PyPI/Homebrew y (si se usa Marker) descargar los pesos del modelo (~2-4GB la primera vez).

## Fase 1 — Inventario y diagnóstico

```bash
python inventario.py /ruta/a/documentos
```

Genera `inventario.csv` (ruta, páginas, tipo nativo/escaneado, imágenes
embebidas, tamaño) clasificando cada PDF por proporción de páginas con texto
seleccionable vs. imagen. Los "escaneados" (ratio_texto bajo) necesitan OCR
real — Marker con `--mode balanced` lo hace; pymupdf4llm no.

## Fase 2 — Piloto (validación de calidad)

Convertir 3-5 PDFs representativos (uno simple, uno con tablas, uno con
muchas imágenes, uno con layout complejo si aplica) y revisar antes de
lanzar el lote completo:

```bash
python convertir_pymupdf.py "carpeta/doc1.pdf" "carpeta/doc2.pdf"
```

Punto de control: comparar contra el PDF original — jerarquía de
encabezados, legibilidad de tablas, enlaces de imágenes. Si un documento
tiene multicolumna mal resuelto, probar el mismo documento con Marker:

```bash
./convertir_marker.sh "carpeta/doc_problema.pdf"
```

## Fase 3 — Conversión por lotes

Con la(s) herramienta(s) ganadora(s) decidida(s) por subconjunto de
documentos:

```bash
python convertir_pymupdf.py archivo1.pdf archivo2.pdf ...
./convertir_marker.sh archivo3.pdf archivo4.pdf ...
./convertir_docx.sh archivo.docx ...
python convertir_pptx.py archivo.pptx ...
```

Todo queda en `output/<misma estructura de carpetas>/<documento>/`, con
imágenes en `assets/` (o `media/` para docx, por defecto de pandoc) y
enlaces relativos al propio `.md` — la carpeta de cada documento es
autocontenida y portable.

`convertir_marker.sh` escribe además `marker_batch.log` con timestamps,
duración y éxito/error por documento.

## Fase 4 — Control de calidad y cierre

Antes de dar por cerrado el lote, validar:

- Ningún `.md` vacío.
- Todos los enlaces de imagen resuelven a archivos existentes dentro de la
  misma carpeta de documento.
- Conteo de encabezados razonable por documento (un `.md` con 0 encabezados
  en un documento largo es señal de que algo salió mal).
- Revisar el log de Marker por warnings de `Table OCR failed` o `Overflow in
  columns/rows` — indican tablas que pueden necesitar revisión manual.

## Problemas conocidos

- **pymupdf4llm 1.28.x**: al usar `write_images=True`, si la ruta de salida
  tiene espacios o paréntesis, el guardado de imágenes falla
  (`code=2: cannot open file`) por una inconsistencia interna entre la ruta
  saneada para el enlace Markdown y la ruta real usada para `pix.save()`.
  Workaround ya aplicado en `convertir_pymupdf.py`: sanear los nombres de
  carpeta propios antes de pasarlos a la librería.
- **surya-ocr 0.22.x** (dependencia de marker-pdf, modo `balanced`): bug de
  gramática GBNF con `\d` que rompe el layout inference en Mac/CPU/MPS. Ver
  `patches/fix_surya_grammar.py`.
- **Multicolumna**: incluso con Marker, revisar manualmente documentos con
  layouts muy irregulares (outlines multinivel, tablas anidadas) — es el
  punto débil común a ambas herramientas.
