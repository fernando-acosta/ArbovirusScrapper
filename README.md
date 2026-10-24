# Puerto Rico Arbovirus Report Scraper

Python tools for downloading Puerto Rico arbovirus surveillance reports, extracting municipal data from **Table 3**, and creating a time-series chart and municipal map of dengue cases for 2026.

The downloader collects original PDFs from the Puerto Rico Department of Health's BioData portal and, by default, also searches the Instituto de Estadísticas de Puerto Rico's current and historical archives. It records source URLs, download results, file sizes, and SHA-256 hashes for traceability.

## Requirements

- Python 3.10 or later.
- Playwright and its Chromium browser for downloading reports.
- Packages in `Main/requirements-extract.txt` for extraction and visualization.
- Internet access for installation, report downloads, and each map run, which downloads Census boundaries.

## Setup

From the `ArboVirusScrapper` repository directory, create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, use `python -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1` in PowerShell.

Install dependencies and Chromium, then enter the scripts directory:

```bash
python -m pip install playwright
python -m playwright install chromium
python -m pip install -r Main/requirements-extract.txt
cd Main
```

On Linux, if Chromium reports missing system libraries, install the browser dependencies with `python -m playwright install --with-deps chromium`.

## Usage

Run these commands from `Main/`, in order:

```bash
# 1. Download reports and create an inventory and ZIP archive.
python descargar_informes_arbovirus.py

# 2. Extract municipal Table 3 data to Excel and CSV.
python extraer_tabla3_arbovirus.py

# 3. Plot municipal case totals by report issue date for 2026.
python graficar_casos_arbovirus_2026.py

# 4. Map municipal counts from the latest issue date in 2026.
python mapa_calor_municipios_2026.py
```

If reports and their inventory are already available, start with extraction. If the extracted CSV is already available, you can run the visualizations directly.

### Download options

| Option | Effect |
| --- | --- |
| `--solo-portal` | Search only BioData; skip the Instituto de Estadísticas archives. |
| `--mostrar-navegador` | Show Chromium to inspect the collection process. |
| `--salida CARPETA` | Set the download directory; defaults to `informes_arbovirus_PR` relative to the working directory. |

```bash
python descargar_informes_arbovirus.py --solo-portal --mostrar-navegador
```

The downloader validates PDF signatures and deduplicates downloaded content by SHA-256 **within a run**. Existing PDFs are retained; repeated runs can create suffixed copies and replace the inventory, summary, and ZIP. Use a fresh output directory when you need an independent collection.

### Extraction options

The default date range is **February 1, 2023 through October 31, 2026**, inclusive. Filtering uses the issue date identified in the report's first three pages, rather than its filename or epidemiological week.

```bash
python extraer_tabla3_arbovirus.py --inicio 2026-01-01 --fin 2026-10-31
```

| Option | Default |
| --- | --- |
| `--pdf-dir` | `Main/informes_arbovirus_PR/PDFs` |
| `--inventario` | `Main/informes_arbovirus_PR/inventario.csv` |
| `--salida` | `Main/tabla3_arbovirus_PR` |
| `--inicio` | `2023-02-01` |
| `--fin` | `2026-10-31` |

Extraction defaults are resolved relative to the script directory. Only PDFs directly inside `--pdf-dir` are processed. The inventory file is required to associate filenames with source URLs.

The extracted Excel and CSV contain these columns:

| Column | Meaning |
| --- | --- |
| `Fecha de emisión` | Report issue date; CSV format is `DD/MM/YYYY`. |
| `Fuente (URL)` | Source URL from the download inventory. |
| `Municipio` | Municipality as extracted from the report. |
| `Frecuencia` | Reported count; annotations may be preserved as text. |
| `Porciento` | Reported percentage. |

### Visualization options

Both visualization scripts accept `--csv RUTA` and `--salida CARPETA`. Their defaults point to `tabla3_arbovirus_PR/` beside the scripts. Both are currently fixed to **2026**.

```bash
python graficar_casos_arbovirus_2026.py --csv tabla3_arbovirus_PR/tabla3_arbovirus_PR.csv --salida resultados
python mapa_calor_municipios_2026.py --csv tabla3_arbovirus_PR/tabla3_arbovirus_PR.csv --salida resultados
```

## Project structure and outputs

```text
ArboVirusScrapper/
├── README.md
├── LICENSE
└── Main/
    ├── descargar_informes_arbovirus.py
    ├── extraer_tabla3_arbovirus.py
    ├── graficar_casos_arbovirus_2026.py
    ├── mapa_calor_municipios_2026.py
    ├── requirements-extract.txt
    ├── informes_arbovirus_PR/
    │   ├── PDFs/                         # Downloaded original reports
    │   ├── descargas_navegador/          # Browser download captures, when present
    │   ├── inventario.csv
    │   └── resumen.json
    ├── informes_arbovirus_PR.zip
    └── tabla3_arbovirus_PR/
        ├── tabla3_arbovirus_PR.xlsx
        ├── tabla3_arbovirus_PR.csv
        ├── errores_extraccion.csv
        ├── resumen.json
        ├── grafica_casos_arbovirus_2026.png
        ├── totales_casos_2026.csv
        ├── mapa_calor_municipios_2026.png
        └── casos_por_municipio_2026.csv
```

The download inventory has columns `fuente`, `archivo`, `estado`, `bytes`, `sha256`, and `url`. Failed links have an `ERROR:` status. The ZIP contains the download directory's files except browser capture files; validated, unique browser captures are also copied into `PDFs/`.

## Data interpretation and limitations

- Collection is best effort. Check the inventory against the source portals before treating the archive as complete.
- Extraction relies on readable PDF text and the expected Table 3 layout. There is no built-in OCR. Review `errores_extraccion.csv` for missing dates, unreadable tables, reading failures, and missing source URLs. PDFs outside the date range are counted separately in the extraction summary.
- The chart sums extracted municipal frequencies for each issue date. These are report snapshots of cumulative counts, not newly reported cases per week. Incomplete extraction can undercount; duplicate reports sharing an issue date can inflate totals because extraction and charting do not deduplicate those rows.
- The map uses the latest **issue date in the input CSV** for 2026 and rejects duplicate municipality entries for that date. It shows counts rather than population-adjusted rates.
- Visualizations use the leading numeric count when a frequency contains annotations. Review the original reports when interpreting corrections or footnotes.
- The scraper covers arbovirus reports, while the supplied visualization scripts label their outputs as dengue. Confirm the meaning of Table 3 in each source report before interpreting extracted data.

## Troubleshooting

- **Missing Playwright or Chromium:** repeat the Playwright installation commands in the active virtual environment.
- **No PDFs downloaded:** check internet access and run with `--mostrar-navegador`; portal changes may require manual downloads or scraper updates.
- **Missing inventory or CSV:** run the preceding pipeline step or provide the appropriate input path explicitly. A custom download directory must also be passed to the extractor using `--pdf-dir` and `--inventario`.
- **No valid 2026 data:** check the extraction date range and whether the CSV contains issue dates in 2026.
- **Map download fails:** check access to the Census download host. The map downloads boundaries on each run.

Each script provides its command-line options through `--help`.

## Sources

- [Puerto Rico Department of Health — BioData arbovirus publications](https://datos.salud.pr.gov/arbovirus/publications)
- [Instituto de Estadísticas — current report archive](https://www.estadisticas.pr.gov/productos/informe-semanal-de-enfermedades-arbovirales)
- [Instituto de Estadísticas — historical report archive](https://www.estadisticas.pr/inventario-de-estadisticas/informe_enfermedades_arbovirales)
- [U.S. Census Bureau — 2024 cartographic county boundaries](https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip), filtered by the map script to Puerto Rico.

## License

Project code is available under the [MIT License](LICENSE), copyright © 2026 Fernando A. Acosta-Perez. Downloaded reports and boundary data remain subject to their respective providers' terms.
