"""Control de calidad + inventario final de la conversión (Fase 4).

Recorre output/, valida cada .md (vacío, sin encabezados, enlaces de imagen
rotos) y genera un inventario_final.csv con el resultado por documento. Si
existe un marker_batch.log en el directorio actual, cruza duración por
documento (match por nombre de archivo).

Uso (ejecutar desde el directorio que contiene output/):
    python qc_inventario.py [directorio_output]
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
IMG_RE = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
LOG_OK_RE = re.compile(r'OK \((\d+)s\): (.+?) ===')


def load_durations(root: Path) -> dict:
    """Parsea marker_batch.log (si existe) y devuelve {nombre_doc: segundos}."""
    log_path = root / "marker_batch.log"
    durations = {}
    if not log_path.exists():
        return durations
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LOG_OK_RE.search(line)
        if m:
            seconds, name = m.groups()
            durations[name.strip()] = durations.get(name.strip(), 0) + int(seconds)
    return durations


def main():
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "output")
    if not output_dir.exists():
        print(f"No existe {output_dir}", file=sys.stderr)
        sys.exit(1)

    durations = load_durations(ROOT)
    mds = sorted(output_dir.rglob("*.md"))
    rows = []

    for md in mds:
        text = md.read_text(encoding="utf-8", errors="replace")
        n_chars = len(text.strip())
        n_headers = sum(1 for line in text.splitlines() if line.strip().startswith("#"))
        img_refs = IMG_RE.findall(text)
        broken = [
            ref for ref in img_refs
            if not ref.startswith("http") and not (md.parent / ref).resolve().exists()
        ]

        estado = "OK"
        if n_chars == 0:
            estado = "ERROR: vacío"
        elif n_headers == 0:
            estado = "REVISION MANUAL: sin encabezados"
        elif broken:
            estado = f"REVISION MANUAL: {len(broken)} enlace(s) roto(s)"

        duracion_s = durations.get(md.stem, "")

        rows.append({
            "ruta_md": str(md.relative_to(ROOT)),
            "duracion_min": round(duracion_s / 60, 1) if duracion_s else "",
            "chars": n_chars,
            "encabezados": n_headers,
            "imagenes": len(img_refs),
            "enlaces_rotos": len(broken),
            "estado": estado,
        })

    out_path = ROOT / "inventario_final.csv"
    fieldnames = ["ruta_md", "duracion_min", "chars", "encabezados", "imagenes", "enlaces_rotos", "estado"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(1 for r in rows if r["estado"] == "OK")
    revision = sum(1 for r in rows if r["estado"].startswith("REVISION"))
    error = sum(1 for r in rows if r["estado"].startswith("ERROR"))
    print(f"{out_path} generado ({len(rows)} documentos)")
    print(f"  OK: {ok} | Revisión manual: {revision} | Error: {error}")
    if revision or error:
        print("\nDocumentos que requieren atención:")
        for r in rows:
            if r["estado"] != "OK":
                print(f"  ! {r['ruta_md']}: {r['estado']}")


if __name__ == "__main__":
    main()
