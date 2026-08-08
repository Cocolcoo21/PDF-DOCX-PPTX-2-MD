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
# --mode balanced (ver detalle de los bugs en patches/*.py):
python patches/fix_surya_grammar.py
python patches/fix_marker_empty_image.py
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
imágenes en `assets/` (o `media/` para docx, por defecto de pandoc; Marker
las deja planas en la misma carpeta que el `.md`) y enlaces relativos al
propio `.md` — la carpeta de cada documento es autocontenida y portable.

`convertir_marker.sh` escribe además `marker_batch.log` con timestamps,
duración y éxito/error por documento, y aplana automáticamente la
subcarpeta redundante que crea `marker_single` (ver Problemas conocidos).

Si un documento falla a mitad de lote (ver Problemas conocidos — el bug de
imagen vacía es el caso típico), el resto del lote sigue: `convertir_marker.sh`
no se detiene en un `ERROR`, solo lo deja registrado en el log. Reintentar
ese documento suelto después con el mismo comando.

## Fase 4 — Control de calidad y cierre

```bash
python qc_inventario.py
```

Recorre `output/`, valida cada `.md` (vacío, sin encabezados, enlaces de
imagen rotos) y genera `inventario_final.csv` con el resultado por
documento — cruza duración desde `marker_batch.log` si existe. Un `.md` con
0 encabezados en un documento largo, o con imágenes referenciadas que no
existen, es señal de que ese documento necesita revisión manual (no
necesariamente un error del pipeline: puede ser que el docx original no use
estilos de encabezado, por ejemplo).

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
- **marker-pdf 2.0.0**: si una caja de layout se recorta a área cero (bbox
  degenerado), Pillow revienta con `ValueError: cannot write empty image as
  JPEG` y aborta la conversión COMPLETA del documento, aunque llevara 20+
  minutos procesado — sin workaround por CLI. Ver
  `patches/fix_marker_empty_image.py` (salta esa imagen puntual con un
  aviso en vez de abortar). Sin issue/fix upstream conocido a la fecha.
- **`marker_single` anida su propio output**: crea `--output_dir/<nombre
  original del archivo>/<archivo>.md` en vez de `--output_dir/<archivo>.md`
  directamente — un nivel de más, y con el nombre *sin sanear* (con
  espacios/paréntesis) aunque `--output_dir` sí esté saneado. `convertir_marker.sh`
  ya lo aplana automáticamente después de cada conversión exitosa.
- **Multicolumna**: incluso con Marker, revisar manualmente documentos con
  layouts muy irregulares (outlines multinivel, tablas anidadas) — es el
  punto débil común a ambas herramientas.

## Procesamiento de imágenes: recomendaciones

Las imágenes se extraen como archivos separados con enlaces relativos
(`assets/imagen.png`), nunca embebidas en base64 dentro del `.md`. Motivos,
confirmados contra prácticas actuales de RAG/pipelines multimodales:

- **Base64 inline infla el archivo ~33%** y vuelve los diffs de git
  ilegibles/gigantes — malo para versionado y para indexar en un pipeline de
  RAG (los chunks de texto quedan contaminados con blobs enormes).
- **El costo en tokens de un modelo de visión (incluido Claude) depende de
  la RESOLUCIÓN de la imagen, no de si se manda como base64 o como
  archivo/URL.** Claude tokeniza en parches de 28×28px: una imagen de
  1000×1000px cuesta ~1,334 tokens sin importar el encoding. Es decir,
  convertir a base64 no ahorra ni cuesta tokens — es puramente un formato de
  transporte.
- Por lo tanto, **el archivo separado es estrictamente mejor para
  almacenamiento/versionado**, y la conversión a base64 (si hace falta,
  porque cierta API solo acepta eso) es una responsabilidad del consumidor
  en el momento de la llamada — no algo que decidir en el momento de la
  conversión PDF→MD.

### Captioning de imágenes (implementado)

Para que el contenido de diagramas/mapas/tablas-como-imagen sea *buscable
por texto* (un RAG de solo texto no puede "ver" una imagen), se genera una
vez, en un paso posterior a la conversión, una descripción corta de cada
imagen vía un modelo con visión, y se inserta como texto justo debajo de la
imagen en el `.md`:

```bash
python caption_imagenes.py --limit 3   # smoke test primero
python caption_imagenes.py             # todo output/
python audit_dedup_captions.py --audit # verificar que cuadre 1 caption/imagen
```

- Usa la API de Claude en paralelo (`MAX_WORKERS = 10` en el script) —
  rápido (minutos, no horas) y barato (~$1-1.50 para varios cientos de
  imágenes con Sonnet). Requiere `ANTHROPIC_API_KEY`.
- **Alternativa 100% local** (sin costo, sin que las imágenes salgan de la
  máquina — preferible si los documentos son sensibles): un modelo de
  visión pequeño vía `llama.cpp`/GGUF (ya instalado si se usó Marker). En
  2026, buenas opciones para Apple Silicon: `Qwen3-VL-4B` (mejor
  calidad/tamaño) o `MiniCPM-V 4.6` (0.8B, el más rápido). No incluido como
  script en este repo todavía — reusar el mismo patrón de
  `llama-server` que usa Marker (ver `patches/`), cambiando el modelo GGUF.
- **Cuidado con la concurrencia**: si varios hilos escriben el mismo `.md`
  en paralelo sin lock, hay *lost updates* (captions que desaparecen sin
  error visible). `caption_imagenes.py` ya usa un lock por archivo — no
  quitarlo si se modifica el script.
- Si el conteo final de captions no coincide exactamente con el de
  imágenes, correr `audit_dedup_captions.py --dedup` (duplicados) y
  `--audit` (faltantes). Una causa posible de faltantes que **no** es un
  bug de este script: Marker a veces duplica una página completa, dejando
  el mismo nombre de imagen referenciado dos veces en el mismo documento —
  la segunda aparición es contenido redundante, no información perdida.

Sources:
- [markitdown issue #2049 — extraer imágenes como archivos separados](https://github.com/microsoft/markitdown/issues/2049)
- [Building a Multimodal LLM Application with PyMuPDF4LLM](https://artifex.com/blog/building-a-multimodal-llm-application-with-pymupdf4llm)
- [Claude Vision docs — cálculo de tokens por imagen](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Multimodal RAG: Retrieving from Images, PDFs, and Tables](https://tensoria.fr/en/blog/multimodal-rag-images-pdfs-tables)
- [Multimodality RAG (MRAG)](https://medium.com/@shivamarora1/multimodality-rag-mrag-extract-store-and-retrieve-visual-data-diagrams-images-from-document-dd47b1892dc8)
