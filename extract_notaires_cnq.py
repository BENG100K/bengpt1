#!/usr/bin/env python3
"""Extract public professional contact details from notairesquebec.org.

The script browses the public directory, opens each profile, clicks the site's
public reveal controls for phone/email, and writes a deduplicated CSV. It uses
low concurrency and delays to reduce load on the website.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

BASE_URL = "https://notairesquebec.org"
DIRECTORY_URL = f"{BASE_URL}/fr"
PROFILE_RE = re.compile(r"^https://notairesquebec\.org/fr/notaire/[A-Za-z0-9_-]+/?$")
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(
    r"(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}"
    r"(?:\s*(?:poste|ext\.?|x)\s*\d+)?",
    re.I,
)
POSTAL_RE = re.compile(
    r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d\b",
    re.I,
)
SPECIALTIES = [
    "Droit immobilier",
    "Testaments et successions",
    "Droit des affaires",
    "Droit de la famille",
    "Médiation",
    "Hypothèques",
    "Mandat de protection",
    "Procuration",
]
FIELDS = [
    "nom",
    "etude",
    "ville",
    "region",
    "adresse",
    "telephone",
    "courriel",
    "domaines_pratique",
    "source",
]


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\r\n,;|")


def save_csv(path: Path, records: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    deduped: dict[str, dict[str, str]] = {}
    for row in records:
        key = row.get("source") or row.get("courriel") or row.get("nom")
        if key:
            deduped[key] = row
    rows = sorted(
        deduped.values(),
        key=lambda r: (r.get("region", "").casefold(), r.get("ville", "").casefold(), r.get("nom", "").casefold()),
    )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


async def collect_profile_urls(page: Page, max_pages: int, delay_ms: int) -> list[str]:
    urls: set[str] = set()
    empty_rounds = 0
    for page_number in range(1, max_pages + 1):
        url = DIRECTORY_URL if page_number == 1 else f"{DIRECTORY_URL}?page={page_number}"
        response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        status = response.status if response else 0
        if status >= 400:
            print(f"Listing page {page_number}: HTTP {status}")
            empty_rounds += 1
            if empty_rounds >= 3:
                break
            continue
        await page.wait_for_timeout(delay_ms)
        hrefs = await page.locator('a[href*="/fr/notaire/"]').evaluate_all(
            "els => els.map(e => e.href)"
        )
        current = {href.split("#", 1)[0].rstrip("/") for href in hrefs if PROFILE_RE.match(href.split("#", 1)[0])}
        before = len(urls)
        urls.update(current)
        added = len(urls) - before
        print(f"Listing {page_number}: {len(current)} profils, {added} nouveaux, total {len(urls)}")
        if not current or added == 0:
            empty_rounds += 1
        else:
            empty_rounds = 0
        if empty_rounds >= 3:
            break
    return sorted(urls)


async def click_reveal(page: Page, pattern: str) -> None:
    candidates = [
        page.get_by_text(re.compile(pattern, re.I), exact=False),
        page.get_by_role("button", name=re.compile(pattern, re.I)),
        page.locator(f'text=/{pattern}/i'),
    ]
    for locator in candidates:
        try:
            count = await locator.count()
            for i in range(min(count, 3)):
                item = locator.nth(i)
                if await item.is_visible():
                    await item.click(timeout=3_000, force=True)
                    await page.wait_for_timeout(350)
                    return
        except Exception:
            continue


async def text_after_h1(page: Page) -> tuple[str, str, str]:
    values = await page.locator("h1").evaluate(
        """el => {
          const out = [];
          let n = el.nextElementSibling;
          while (n && out.length < 4) {
            const t = (n.innerText || n.textContent || '').trim();
            if (t) out.push(t);
            n = n.nextElementSibling;
          }
          return out;
        }"""
    )
    etude = clean(values[0]) if values else ""
    location = ""
    for value in values[1:]:
        candidate = clean(value)
        if "," in candidate and len(candidate) < 100:
            location = candidate
            break
    if not location:
        body_lines = [clean(x) for x in (await page.locator("body").inner_text()).splitlines() if clean(x)]
        for line in body_lines:
            if "," in line and len(line) < 100 and not POSTAL_RE.search(line):
                location = line
                break
    city, region = "", ""
    if "," in location:
        city, region = [clean(x) for x in location.split(",", 1)]
    return etude, city, region


async def extract_profile(page: Page, url: str, delay_ms: int) -> dict[str, str]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            status = response.status if response else 0
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")
            await page.wait_for_timeout(delay_ms)
            await click_reveal(page, r"révéler le numéro|reveal.*phone")
            await click_reveal(page, r"révéler le courriel|reveal.*email")
            await page.wait_for_timeout(350)

            nom = clean(await page.locator("h1").first.inner_text(timeout=5_000))
            nom = re.sub(r"^Me\s+", "", nom, flags=re.I)
            etude, ville, region = await text_after_h1(page)
            body = clean(await page.locator("body").inner_text())

            email = ""
            mail_links = page.locator('a[href^="mailto:"]')
            if await mail_links.count():
                href = await mail_links.first.get_attribute("href") or ""
                email = clean(href.split(":", 1)[-1].split("?", 1)[0]).lower()
            if not email:
                match = EMAIL_RE.search(body)
                email = match.group(0).lower() if match else ""

            telephone = ""
            tel_links = page.locator('a[href^="tel:"]')
            if await tel_links.count():
                href = await tel_links.first.get_attribute("href") or ""
                telephone = clean(href.split(":", 1)[-1])
            if not telephone:
                match = PHONE_RE.search(body)
                telephone = clean(match.group(0)) if match else ""

            adresse = ""
            for line in [clean(x) for x in (await page.locator("body").inner_text()).splitlines() if clean(x)]:
                if POSTAL_RE.search(line) and re.search(r"\d", line):
                    adresse = line
                    break

            domaines = [specialty for specialty in SPECIALTIES if specialty.casefold() in body.casefold()]
            return {
                "nom": nom,
                "etude": etude,
                "ville": ville,
                "region": region,
                "adresse": adresse,
                "telephone": telephone,
                "courriel": email,
                "domaines_pratique": "; ".join(domaines),
                "source": url,
            }
        except Exception as exc:
            last_error = exc
            await page.wait_for_timeout(1_000 * (attempt + 1))
    raise RuntimeError(f"Échec profil {url}: {last_error}")


async def worker(
    worker_id: int,
    context: BrowserContext,
    queue: asyncio.Queue[str],
    records: list[dict[str, str]],
    errors: list[str],
    lock: asyncio.Lock,
    output: Path,
    delay_ms: int,
) -> None:
    page = await context.new_page()
    try:
        while True:
            try:
                url = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                row = await extract_profile(page, url, delay_ms)
                async with lock:
                    records.append(row)
                    count = len(records)
                    print(f"Worker {worker_id}: {count} profils extraits — {row['nom']}")
                    if count % 50 == 0:
                        save_csv(output, records)
            except Exception as exc:
                async with lock:
                    errors.append(str(exc))
                    print(f"Worker {worker_id}: ERREUR {exc}")
            finally:
                queue.task_done()
    finally:
        await page.close()


async def run(args: argparse.Namespace) -> None:
    output = Path(args.output)
    records: list[dict[str, str]] = []
    errors: list[str] = []
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            locale="fr-CA",
            viewport={"width": 1440, "height": 1100},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )
        listing_page = await context.new_page()
        try:
            urls = await collect_profile_urls(listing_page, args.max_pages, args.delay_ms)
            Path("profile_urls.txt").write_text("\n".join(urls), encoding="utf-8")
            if not urls:
                raise RuntimeError("Aucun profil trouvé dans le répertoire")
            if args.limit:
                urls = urls[: args.limit]
            print(f"Début extraction de {len(urls)} profils avec {args.workers} workers")
            queue: asyncio.Queue[str] = asyncio.Queue()
            for url in urls:
                queue.put_nowait(url)
            lock = asyncio.Lock()
            tasks = [
                asyncio.create_task(
                    worker(i + 1, context, queue, records, errors, lock, output, args.delay_ms)
                )
                for i in range(args.workers)
            ]
            await asyncio.gather(*tasks)
            save_csv(output, records)
            Path("errors.txt").write_text("\n".join(errors), encoding="utf-8")
            print(
                f"Terminé: {len(records)} profils extraits, {len(errors)} erreurs, "
                f"CSV: {output}"
            )
        finally:
            await listing_page.close()
            await context.close()
            await browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extraire le répertoire public des notaires du Québec")
    parser.add_argument("--output", default="notaires_quebec.csv")
    parser.add_argument("--max-pages", type=int, default=400)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay-ms", type=int, default=650)
    parser.add_argument("--limit", type=int, default=0, help="Limiter le nombre de profils pour un test")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
