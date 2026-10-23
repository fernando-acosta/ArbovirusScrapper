#!/usr/bin/env python3
"""Grafica la suma municipal de Tabla 3 por fecha de emisión para 2026."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit(
        "Falta matplotlib. Instálalo con: "
        "python -m pip install -r requirements-extract.txt"
    )


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = (
    SCRIPT_DIR / "tabla3_arbovirus_PR" / "tabla3_arbovirus_PR.csv"
)
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "tabla3_arbovirus_PR"
DATE_FORMAT = "%d/%m/%Y"


def read_daily_totals(csv_path: Path) -> list[tuple[datetime, int]]:
    totals: defaultdict[datetime, int] = defaultdict(int)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"Fecha de emisión", "Frecuencia"}
        if not required.issubset(reader.fieldnames or []):
            missing = ", ".join(sorted(required - set(reader.fieldnames or [])))
            raise ValueError(f"Faltan columnas en el CSV: {missing}")
        for line_number, row in enumerate(reader, start=2):
            try:
                issued = datetime.strptime(row["Fecha de emisión"], DATE_FORMAT)
                if issued.year != 2026:
                    continue
                count = re.match(r"\s*(\d[\d,]*)", row["Frecuencia"])
                if count is None:
                    raise ValueError("frecuencia no numérica")
                totals[issued] += int(count.group(1).replace(",", ""))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Fila {line_number}: no se pudo leer fecha/frecuencia: {exc}"
                ) from exc
    if not totals:
        raise ValueError("El CSV no contiene filas válidas con fecha de emisión de 2026.")
    return sorted(totals.items())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crear una gráfica de línea de casos acumulados de dengue en 2026."
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--salida", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    if not args.csv.is_file():
        parser.error(f"No se encontró el CSV: {args.csv}")

    try:
        daily_totals = read_daily_totals(args.csv)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    args.salida.mkdir(parents=True, exist_ok=True)
    chart_path = args.salida / "grafica_casos_arbovirus_2026.png"
    summary_path = args.salida / "totales_casos_2026.csv"

    with summary_path.open("w", encoding="utf-8-sig", newline="") as summary_file:
        writer = csv.writer(summary_file)
        writer.writerow(["Fecha de emisión", "Casos acumulados (suma del CSV)"])
        writer.writerows(
            (issued.strftime(DATE_FORMAT), total) for issued, total in daily_totals
        )

    dates = [issued for issued, _ in daily_totals]
    counts = [total for _, total in daily_totals]
    fig, ax = plt.subplots(figsize=(11, 6.5))
    fig.subplots_adjust(bottom=0.2)
    ax.plot(
        dates,
        counts,
        color="#1769aa",
        marker="o",
        markersize=6,
        linewidth=2,
    )
    for issued, total in daily_totals:
        ax.annotate(
            f"{total:,}",
            (issued, total),
            textcoords="offset points",
            xytext=(0, 9),
            ha="center",
            fontsize=8,
        )
    ax.set_title("Casos acumulados de dengue en Puerto Rico — 2026")
    ax.set_xlabel("Fecha de emisión del informe")
    ax.set_ylabel("Suma de frecuencias municipales")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=12))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_ylim(bottom=0)
    fig.text(
        0.01,
        0.01,
        "Suma las frecuencias municipales disponibles en el CSV; puede haber subextracciones. "
        "Fechas = emisión de los informes.",
        ha="left",
        fontsize=8,
        color="#555555",
    )
    fig.savefig(chart_path, dpi=180)
    plt.close(fig)

    print(f"Informes graficados: {len(daily_totals)}")
    print(f"Gráfica: {chart_path}")
    print(f"Totales por fecha: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
