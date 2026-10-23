#!/usr/bin/env python3
"""Descarga los informes PDF de BioData (arbovirus) y, como respaldo, los del Instituto de Estadísticas.

Requisitos: pip install playwright; python -m playwright install chromium
Uso: python descargar_informes_arbovirus.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import unicodedata
import zipfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    sys.exit("Falta Playwright. Ejecuta: python -m pip install playwright && python -m playwright install chromium")

PORTAL = "https://datos.salud.pr.gov/arbovirus/publications"
MIRROR = "https://www.estadisticas.pr.gov/productos/informe-semanal-de-enfermedades-arbovirales"
HISTORIC = "https://www.estadisticas.pr/inventario-de-estadisticas/informe_enfermedades_arbovirales"
PDF_RE = re.compile(r"(?i)(?:\.pdf(?:[?#]|$)|/download(?:/|\?|$)|/descargar(?:/|\?|$))")
URL_IN_TEXT = re.compile(r"(?i)(?:https?:)?//[^\s\"'<>\\]+?\.pdf(?:\?[^\s\"'<>\\]*)?|(?:/[a-z0-9_./%~-]+)+\.pdf(?:\?[^\s\"'<>\\]*)?")
NEXT_RE = re.compile(r"^(?:next|next page|siguiente|pr[oó]xima|p[aá]gina siguiente|›|»|→)$", re.I)
FILES_DIR = "PDFs"


def pdfish(s: str) -> bool:
    return bool(PDF_RE.search(s))


def absolute(value: str, base: str) -> str | None:
    value = html.unescape(str(value).strip().replace('\\/', '/')).strip('"\'<>')
    if not value or value.startswith(('blob:', 'data:', 'javascript:', 'mailto:', '#')):
        return None
    url = urljoin(base, value)
    p = urlsplit(url)
    if p.scheme not in ('http', 'https'):
        return None
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))


def clean_filename(s: str, maxlen=135) -> str:
    s = unquote(s)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if ch.isascii())
    s = re.sub(r'[^A-Za-z0-9_.-]+', '_', s).strip('._-')
    if not s:
        s = 'informe_arbovirus'
    return s[:maxlen]


def try_pdf_link(value, base, add, source):
    if isinstance(value, str):
        for found in [value] + URL_IN_TEXT.findall(value):
            u = absolute(found, base)
            if u and pdfish(u):
                add(u, source)


def extract_nested(obj, base, add, source, depth=0):
    if depth > 14:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                try_pdf_link(v, base, add, source)
            else:
                extract_nested(v, base, add, source, depth+1)
    elif isinstance(obj, list):
        for v in obj[:2500]:
            extract_nested(v, base, add, source, depth+1)
    elif isinstance(obj, str):
        try_pdf_link(obj, base, add, source)


def extract_dom(page, add, source):
    try:
        rows = page.locator('a[href], iframe[src], embed[src], object[data], [data-href], [data-url]').evaluate_all(
            "els => els.map(e => ({v: e.href || e.src || e.data || e.getAttribute('data-href') || e.getAttribute('data-url'), t: (e.innerText || e.textContent || '').slice(0,100)}))"
        )
        for row in rows:
            val = row.get('v') or ''
            text = row.get('t') or ''
            # A link labelled 'PDF' may point to a direct download service without a .pdf extension.
            u = absolute(val, page.url)
            if u and (pdfish(u) or ('pdf' in text.lower() and '/publications' not in u and '/arbovirus' not in u)):
                add(u, source)
        # Embedded JSON/HTML sometimes contains the direct URL outside an <a> element.
        for found in URL_IN_TEXT.findall(page.content()):
            try_pdf_link(found, page.url, add, source)
    except Exception as e:
        print(f'  Aviso: no se pudo inspeccionar HTML: {e}')


def trigger_download_controls(page, clicked, max_per_view=80):
    """Activa controles de descarga en una lista dinámica cuando no exponen un href PDF.

    Su propósito es provocar descargas o llamadas de red que luego se registran
    por los listener de descargas/respuestas. Excluye controles de navegación.
    """
    selector = 'button, [role="button"], a[href]'
    try:
        candidates = page.locator(selector).evaluate_all("""els => els.map((el, i) => {
          const svg = el.querySelector('svg');
          return {i, title: [el.innerText, el.getAttribute('aria-label'), el.getAttribute('title'),
                    el.getAttribute('data-tooltip'), svg && svg.outerHTML.slice(0,300)].filter(Boolean).join(' '),
                  href: el.getAttribute('href') || '',
                  vicinity: el.closest('tr,li,article,[role=row]')?.innerText.slice(0,150) || ''};
        })""")
    except Exception:
        return
    count = 0
    for x in candidates:
        if count >= max_per_view:
            break
        label = (x['title'] or '').lower()
        if not re.search(r'(?i)descargar|download|\bpdf\b|file.download|file_download|descarga', label):
            continue
        if pdfish(x.get('href','')):
            continue
        # Skip non-report global navigation controls.
        if re.search(r'(instalar|app store|cookies|imprimir|share)',label):
            continue
        key = (page.url, x['i'], x.get('vicinity', '')[:100])
        if key in clicked:
            continue
        clicked.add(key)
        try:
            el = page.locator(selector).nth(x['i'])
            if el.is_visible() and el.is_enabled():
                el.click(timeout=3000)
                page.wait_for_timeout(350)
                count += 1
        except Exception:
            continue
    if count:
        print(f'  Se activaron {count} controles de descarga en esta pantalla.')


def scroll(page):
    try:
        last = 0
        for _ in range(10):
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(600)
            height = page.evaluate('document.body.scrollHeight')
            if height == last:
                break
            last = height
        page.evaluate('window.scrollTo(0,0)')
    except Exception:
        pass


def make_response_listener(add, source):
    def handler(response):
        try:
            ctype = response.headers.get('content-type', '').lower()
            if ('pdf' in ctype or pdfish(response.url)) and not response.url.startswith('blob:'):
                add(response.url, source)
            elif 'json' in ctype and response.request.resource_type in ('xhr', 'fetch'):
                # A published list can be returned as JSON even if the DOM displays pagination.
                if int(response.headers.get('content-length') or 0) > 5_000_000:
                    return
                try:
                    extract_nested(response.json(), response.url, add, source + ' (API)')
                except Exception:
                    pass
        except Exception:
            pass
    return handler


def crawl_portal(browser, add, outdir):
    ctx = browser.new_context(accept_downloads=True, locale='es-PR')
    page = ctx.new_page()
    page.set_default_timeout(6000)
    ctx.on('response', make_response_listener(add, 'BioData'))
    acquired_downloads = []

    def on_download(download):
        try:
            name = clean_filename(download.suggested_filename)
            dest = outdir / 'descargas_navegador' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = dest.with_name(dest.stem + '_' + str(len(acquired_downloads)) + dest.suffix)
            download.save_as(dest)
            acquired_downloads.append((str(dest), download.url))
            print('  Archivo de descarga del navegador:', name)
        except Exception as exc:
            print('  Aviso al guardar descarga:', exc)

    page.on('download', on_download)
    ctx.on('page', lambda new_page: new_page.on('download', on_download))
    clicked_controls = set()
    print('\n1) Explorando BioData...', flush=True)
    try:
        page.goto(PORTAL, wait_until='domcontentloaded', timeout=45000)
        page.wait_for_timeout(4500)
        scroll(page)
        extract_dom(page, add, 'BioData')
        trigger_download_controls(page, clicked_controls)

        # Visit visible pages; these common next-page controls are safe to click.
        seen = set()
        for i in range(150):
            scroll(page)
            extract_dom(page, add, 'BioData')
            trigger_download_controls(page, clicked_controls)
            signature = hashlib.md5(re.sub(r'\s+', ' ', page.locator('body').inner_text()[:20000]).encode()).hexdigest()
            if signature in seen:
                break
            seen.add(signature)
            next_button = page.get_by_role('button', name=NEXT_RE).first
            if not next_button.count() or not next_button.is_visible() or not next_button.is_enabled():
                next_button = page.get_by_role('link', name=NEXT_RE).first
            if not next_button.count() or not next_button.is_visible() or not next_button.is_enabled():
                break
            try:
                next_button.click(timeout=3500)
                page.wait_for_timeout(900)
            except Exception:
                break
        print(f'  Se inspeccionaron {len(seen)} pantallas del portal.')

        # Independently inspect common year filters, without assuming a particular site framework.
        for select in page.locator('select').all()[:8]:
            try:
                if not select.is_visible():
                    continue
                options = select.locator('option').evaluate_all("xs => xs.map(o => ({value:o.value, text:o.textContent}))")
                year_options = [o for o in options if re.search(r'20(?:1[5-9]|2[0-9])', o['text'])]
                if not year_options:
                    continue
                for opt in year_options[:20]:
                    select.select_option(value=opt['value'])
                    page.wait_for_timeout(900)
                    scroll(page)
                    extract_dom(page, add, 'BioData')
                    trigger_download_controls(page, clicked_controls)
            except Exception:
                pass
        # Scan the DOM for year tabs or buttons, in case the site uses this instead of a <select>.
        for year in range(datetime.now().year, 2015, -1):
            try:
                candidates = page.get_by_role('button', name=str(year), exact=True)
                if not candidates.count():
                    candidates = page.get_by_role('tab', name=str(year), exact=True)
                if candidates.count() and candidates.first.is_visible():
                    candidates.first.click(timeout=2400)
                    page.wait_for_timeout(700)
                    scroll(page)
                    extract_dom(page, add, 'BioData')
                    trigger_download_controls(page, clicked_controls)
            except Exception:
                pass
        page.wait_for_timeout(1200)
    except Exception as exc:
        print('  Aviso: no fue posible explorar completamente BioData:', exc)
    finally:
        ctx.close()
    return acquired_downloads


def crawl_mirror(browser, add, base, param, source, maxpages=60):
    ctx = browser.new_context(locale='es-PR')
    page = ctx.new_page()
    print(f'\n2) Buscando archivo histórico: {source}...', flush=True)
    misses = 0
    last_count = 0
    for i in range(1, maxpages+1):
        sep = '&' if '?' in base else '?'
        url = base if i == 1 else f'{base}{sep}{param}={i}'
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=25000)
            page.wait_for_timeout(650)
            extract_dom(page, add, source)
        except Exception as exc:
            print(f'  Aviso página {i}: {exc}')
        count = add('COUNT', source)
        if count == last_count:
            misses += 1
        else:
            misses = 0
            print(f'  Página {i}: {count} enlaces PDF únicos identificados (acumulado)')
        last_count = count
        if misses >= 2:
            break
    ctx.close()


def get_actual_pdf(api, url, destination, expected_name):
    try:
        response = api.get(url, timeout=45000, max_redirects=10)
        status = response.status
        if status != 200:
            return False, f'HTTP {status}', 0
        body = response.body()
        if not body.lstrip().startswith(b'%PDF-'):
            return False, f'No es PDF (content-type={response.headers.get("content-type", "?")})', len(body)
        destination.write_bytes(body)
        return True, 'OK', len(body)
    except Exception as exc:
        return False, str(exc)[:160], 0


def main():
    ap = argparse.ArgumentParser(description='Descargar todos los PDFs detectables de arbovirus')
    ap.add_argument('--salida', default='informes_arbovirus_PR', help='Carpeta de resultados')
    ap.add_argument('--solo-portal', action='store_true', help='Excluir archivos de respaldo')
    ap.add_argument('--mostrar-navegador', action='store_true', help='Mostrar Chromium')
    args = ap.parse_args()
    root = Path(args.salida).expanduser().resolve()
    target = root / FILES_DIR
    target.mkdir(parents=True, exist_ok=True)
    found = OrderedDict()

    def add(url, source):
        if url == 'COUNT':
            return len(found)
        u = absolute(url, PORTAL)
        if u and u not in found:
            found[u] = source

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.mostrar_navegador)
        browser_downloads = crawl_portal(browser, add, root)
        if not args.solo_portal:
            crawl_mirror(browser, add, MIRROR, 'f85c2126_page', 'Instituto de Estadísticas (actual)')
            crawl_mirror(browser, add, HISTORIC, 'page', 'Instituto de Estadísticas (histórico)', maxpages=35)
        print(f'\nSe detectaron {len(found)} URL posibles de PDFs. Descargando...', flush=True)
        api = p.request.new_context(ignore_https_errors=False, timeout=45000)
        rows = []
        hashes = {}
        for index, (url, source) in enumerate(found.items(), 1):
            basename = Path(urlsplit(url).path).name
            basename = clean_filename(basename)
            if not basename.lower().endswith('.pdf'):
                basename = f'informe_arbovirus_{index:04d}.pdf'
            stem = basename.removesuffix('.pdf')
            filename = basename
            n = 2
            while (target / filename).exists():
                filename = f'{stem}_{n}.pdf'
                n += 1
            destination = target / filename
            ok, note, size = get_actual_pdf(api, url, destination, filename)
            digest = ''
            if ok:
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                if digest in hashes:
                    destination.unlink()
                    filename = hashes[digest]
                    note = 'Duplicado del archivo ' + filename
                else:
                    hashes[digest] = filename
            rows.append({'fuente':source,'archivo':filename if ok else '', 'estado':note if ok else 'ERROR: '+note,
                         'bytes':size, 'sha256':digest, 'url':url})
            if index % 10 == 0 or not ok:
                print(f'  {index}/{len(found)} - {"OK" if ok else "FALLÓ"} - {filename} - {note}', flush=True)
        # Some portals download PDFs only after clicking a button. Preserve those captures too.
        for path, url in browser_downloads:
            fp = Path(path)
            if fp.exists() and fp.read_bytes().lstrip().startswith(b'%PDF-'):
                data = fp.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                if digest not in hashes:
                    dst = target / fp.name
                    i = 2
                    while dst.exists():
                        dst = target / f'{fp.stem}_{i}{fp.suffix}'
                        i += 1
                    dst.write_bytes(data)
                    hashes[digest] = dst.name
                    rows.append({'fuente':'BioData (descarga del navegador)','archivo':dst.name,'estado':'OK',
                                 'bytes':len(data),'sha256':digest,'url':url})
        api.dispose()
        browser.close()

    with (root/'inventario.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w = csv.DictWriter(f, fieldnames=['fuente','archivo','estado','bytes','sha256','url'])
        w.writeheader()
        w.writerows(rows)
    summary = {'fecha_ejecucion':datetime.now().isoformat(timespec='seconds'),
               'pdfs_unicos_guardados':len(hashes),'enlaces_detectados':len(found),
               'descargas_fallidas':sum(r['estado'].startswith('ERROR:') for r in rows),
               'portal_revisado':PORTAL,'nota':'La exhaustividad depende de los enlaces y años expuestos por los portales.'}
    (root/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    zip_path = root.parent / f'{root.name}.zip'
    with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for fp in sorted(root.rglob('*')):
            if fp.is_file() and 'descargas_navegador' not in fp.parts:
                z.write(fp,arcname=fp.relative_to(root))
    print('\n'+json.dumps(summary,indent=2,ensure_ascii=False))
    print(f'\nZIP listo: {zip_path}')
    print(f'Inventario: {root/"inventario.csv"}')
    if not hashes:
        print('\nATENCIÓN: 0 PDFs descargados. Verifica acceso a Internet o ejecuta --mostrar-navegador.')


if __name__ == '__main__':
    main()
