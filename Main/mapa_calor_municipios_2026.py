#!/usr/bin/env python3
"""Crear un mapa por municipio de los casos acumulados de dengue reportados en 2026."""
from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

try:
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    import truststore
except ImportError:
    sys.exit(
        "Faltan dependencias. Instálalas con: "
        "python -m pip install -r requirements-extract.txt"
    )

truststore.inject_into_ssl()


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = SCRIPT_DIR / "tabla3_arbovirus_PR" / "tabla3_arbovirus_PR.csv"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "tabla3_arbovirus_PR"
CENSUS_BOUNDARIES_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2024/shp/"
    "cb_2024_us_county_500k.zip"
)
DATE_FORMAT = "%d/%m/%Y"
FREQUENCY_RE = re.compile(r"^\s*(\d[\d,]*)")


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        char.lower()
        for char in decomposed
        if not unicodedata.combining(char) and char.isalnum()
    )


def load_latest_report(csv_path: Path) -> tuple[datetime, dict[str, int]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"Fecha de emisión", "Municipio", "Frecuencia"}
        if not required.issubset(reader.fieldnames or []):
            missing = ", ".join(sorted(required - set(reader.fieldnames or [])))
            raise ValueError(f"Faltan columnas en el CSV: {missing}")
        parsed: list[tuple[datetime, str, int]] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                issue_date = datetime.strptime(row["Fecha de emisión"], DATE_FORMAT)
                if issue_date.year != 2026:
                    continue
                match = FREQUENCY_RE.match(row["Frecuencia"])
                if match is None:
                    raise ValueError("frecuencia no numérica")
                parsed.append(
                    (
                        issue_date,
                        row["Municipio"].strip(),
                        int(match.group(1).replace(",", "")),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Fila {line_number}: {exc}") from exc
    if not parsed:
        raise ValueError("El CSV no contiene datos con fecha de emisión de 2026.")

    latest_date = max(issue_date for issue_date, _, _ in parsed)
    latest_rows = [
        (municipality, count)
        for issue_date, municipality, count in parsed
        if issue_date == latest_date
    ]
    counts: dict[str, int] = {}
    for municipality, count in latest_rows:
        key = normalize_name(municipality)
        if key in counts:
            raise ValueError(
                f"Municipio duplicado para el informe más reciente: {municipality}"
            )
        counts[key] = count
    return latest_date, counts


def download_boundaries(destination: Path) -> Path:
    request = urllib.request.Request(
        CENSUS_BOUNDARIES_URL,
        headers={"User-Agent": "arbovirus-report-map/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            archive_bytes = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(
            f"No se pudieron descargar los límites municipales del Censo: {exc}"
        ) from exc

    archive_path = destination / "census_boundaries.zip"
    archive_path.write_bytes(archive_bytes)
    with zipfile.ZipFile(archive_path) as archive:
        shapefile = next(
            (
                name
                for name in archive.namelist()
                if name.lower().endswith(".shp")
                and Path(name).name == "cb_2024_us_county_500k.shp"
            ),
            None,
        )
        if shapefile is None:
            raise ValueError("El archivo de límites del Censo no contiene el shapefile esperado.")
        extracted_names: list[Path] = []
        for member in archive.namelist():
            if Path(member).stem != Path(shapefile).stem:
                continue
            if Path(member).suffix.lower() not in {".shp", ".shx", ".dbf", ".prj", ".cpg"}:
                continue
            destination_path = (destination / Path(member).name).resolve()
            if not destination_path.is_relative_to(destination.resolve()):
                raise ValueError("Ruta inesperada en el archivo de límites.")
            with archive.open(member) as src, destination_path.open("wb") as dst:
                dst.write(src.read())
            if destination_path.suffix.lower() == ".shp":
                extracted_names.append(destination_path)
    if not extracted_names:
        raise ValueError("No se pudo extraer el shapefile municipal.")
    return extracted_names[0]


def make_map(csv_path: Path, output_dir: Path) -> tuple[Path, Path, datetime, int]:
    issue_date, counts = load_latest_report(csv_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arbovirus_map_") as temp_dir:
        shapefile = download_boundaries(Path(temp_dir))
        boundaries = gpd.read_file(shapefile)
    boundaries = boundaries.loc[boundaries["STATEFP"] == "72"].copy()
    if len(boundaries) != 78:
        raise ValueError(
            f"Se esperaban 78 municipios de Puerto Rico; el Censo devolvió {len(boundaries)}."
        )

    boundaries["municipio_key"] = boundaries["NAME"].map(normalize_name)
    names = set(boundaries["municipio_key"])
    unknown = sorted(set(counts) - names)
    if unknown:
        raise ValueError(
            "Hay municipios del CSV que no coinciden con los límites del Censo: "
            + ", ".join(unknown)
        )
    boundaries["casos"] = boundaries["municipio_key"].map(counts).fillna(0).astype(int)
    total_cases = sum(counts.values())
    if int(boundaries["casos"].sum()) != total_cases:
        raise ValueError("El total cartografiado no coincide con la suma del CSV.")
    boundaries = boundaries.to_crs("EPSG:32161")

    map_path = output_dir / "mapa_calor_municipios_2026.png"
    data_path = output_dir / "casos_por_municipio_2026.csv"
    display = boundaries[["NAME", "GEOID", "casos"]].rename(
        columns={"NAME": "Municipio", "GEOID": "FIPS"}
    )
    display.sort_values("Municipio").to_csv(
        data_path, index=False, encoding="utf-8-sig"
    )

    fig, ax = plt.subplots(figsize=(12, 8))
    boundaries.plot(
        column="casos",
        ax=ax,
        cmap="YlOrRd",
        norm=Normalize(vmin=0, vmax=max(int(boundaries["casos"].max()), 1)),
        edgecolor="#ffffff",
        linewidth=0.55,
        legend=True,
        legend_kwds={
            "label": "Casos acumulados reportados",
            "shrink": 0.72,
            "orientation": "vertical",
        },
        missing_kwds={"color": "#eeeeee"},
    )
    for _, feature in boundaries.iterrows():
        point = feature.geometry.representative_point()
        cases = int(feature["casos"])
        color = "#ffffff" if cases >= 70 else "#292929"
        ax.annotate(
            str(cases),
            (point.x, point.y),
            ha="center",
            va="center",
            fontsize=5.5,
            color=color,
        )
    ax.set_title(
        "Casos acumulados de dengue por municipio — Puerto Rico, 2026\n"
        f"Informe más reciente disponible: {issue_date.strftime('%d/%m/%Y')} "
        f"| Total: {total_cases:,} casos",
        fontsize=14,
        pad=16,
    )
    ax.set_axis_off()
    fig.text(
        0.5,
        0.025,
        "Fuente de datos: CSV de Tabla 3. Los municipios ausentes en esa tabla "
        "se muestran con 0. Límites municipales: U.S. Census Bureau, TIGER/Line 2024. "
        "No es una tasa ajustada por población.",
        ha="center",
        fontsize=8,
        color="#555555",
        wrap=True,
    )
    fig.subplots_adjust(bottom=0.1)
    fig.savefig(map_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return map_path, data_path, issue_date, total_cases


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crear un mapa de calor de casos acumulados por municipio para 2026."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--salida", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    if not args.csv.is_file():
        parser.error(f"No se encontró el CSV: {args.csv}")
    try:
        map_path, data_path, issue_date, total = make_map(args.csv, args.salida)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(f"Fecha del informe: {issue_date.strftime(DATE_FORMAT)}")
    print(f"Casos acumulados: {total}")
    print(f"Mapa: {map_path}")
    print(f"Datos por municipio: {data_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
