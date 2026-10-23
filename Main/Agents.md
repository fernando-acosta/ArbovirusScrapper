# DESCARGADOR DE INFORMES PDF DE ARBOVIRUS - PUERTO RICO

## OBJETIVO
Recopila los PDF de https://datos.salud.pr.gov/arbovirus/publications
Además busca informes en el archivo público del Instituto de Estadísticas.
Genera informes_arbovirus_PR.zip, con PDFs originales que pudieron descargarse,
un inventario CSV de enlaces y un resumen de errores/archivos.

## MAC (más sencillo)
1. Descomprime el ZIP descargado de ChatGPT.
2. Abre Terminal en la carpeta que contiene estos archivos.
3. Ejecuta: bash ejecutar_mac.command
   La primera ejecución instala Chromium y el paquete Playwright en .venv.
   Deberás tener acceso a Internet en tu computadora.
4. Al finalizar, abre informes_arbovirus_PR.zip.
5. Revisa inventario.csv para conocer qué PDFs se obtuvieron y cuáles fallaron.

## WINDOWS / LINUX
1. Instala Python 3.10 o más reciente.
2. Abre una terminal en esta carpeta.
3. Ejecuta:
   python -m pip install playwright
   python -m playwright install chromium
   python descargar_informes_arbovirus.py
4. Abre informes_arbovirus_PR.zip y revisa inventario.csv.

## EXTRACCIÓN DE TABLA 3
1. Instala las dependencias de extracción:
   python -m pip install -r requirements-extract.txt
2. Ejecuta:
   python extraer_tabla3_arbovirus.py
3. Revisa tabla3_arbovirus_PR/tabla3_arbovirus_PR.xlsx y
   tabla3_arbovirus_PR/tabla3_arbovirus_PR.csv.
   El extractor usa la fecha de emisión impresa en cada informe y, por defecto,
   incluye fechas del 1 de febrero de 2023 al 31 de octubre de 2026.
4. Revisa errores_extraccion.csv para informes sin fecha, con tabla ilegible o
   con un problema de lectura. Los PDF escaneados pueden requerir OCR.

## GRÁFICA DE CASOS ACUMULADOS DE 2026
Ejecuta:
   python graficar_casos_arbovirus_2026.py
La gráfica y los totales por fecha se guardan en tabla3_arbovirus_PR/.

## MAPA DE CASOS POR MUNICIPIO DE 2026
Instala las dependencias indicadas en requirements-extract.txt y ejecuta:
   python mapa_calor_municipios_2026.py
El mapa usa los conteos del informe de 2026 más reciente presente en el CSV.
Descarga los límites municipales TIGER/Line del Censo de EE. UU. y guarda el
PNG y la tabla de conteos por municipio en tabla3_arbovirus_PR/.

## OPCIONES
  --solo-portal         No incorpora el archivo adicional del Instituto de Estadísticas.
  --mostrar-navegador   Abre el navegador para inspección visual.
  --salida CARPETA      Cambia la carpeta de resultados.

## NOTAS IMPORTANTES
- El recopilador hace un mejor esfuerzo; un sitio web con botones no estándar,
  formularios o peticiones ocultas puede requerir descarga manual complementaria.
- No afirmar que el conjunto está completo sin comprobarlo con la página fuente.
- El inventario identifica explícitamente los enlaces que fallaron.
- No se alteran los PDF descargados; se comprueba que comienzan con la firma %PDF-.
