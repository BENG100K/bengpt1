#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import re
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://trouverunnotaire.cnq.org/"
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?:\s*(?:poste|ext\.?|x)\s*\d+)?", re.I)


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" ,;|\n\t")


async def fill_city(page, value: str) -> bool:
    candidates = [
        page.get_by_label(re.compile("ville|municipalit|city", re.I)),
        page.get_by_placeholder(re.compile("ville|municipalit|city|adresse", re.I)),
        page.locator('input[name*="ville" i], input[id*="ville" i], input[name*="city" i], input[id*="city" i]'),
        page.locator('input[type="search"]'),
        page.locator('input[type="text"]'),
    ]
    for locator in candidates:
        try:
            count = await locator.count()
            for i in range(count):
                item = locator.nth(i)
                if await item.is_visible() and await item.is_enabled():
                    await item.fill(value)
                    await page.wait_for_timeout(800)
                    try:
                        suggestion = page.get_by_text(re.compile(rf"^{re.escape(value)}(?:\b|,)", re.I)).first
                        if await suggestion.count() and await suggestion.is_visible():
                            await suggestion.click(timeout=1500)
                    except Exception:
                        pass
                    return True
        except Exception:
            pass
    return False


async def main_async(city: str, radius: int, output: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(locale="fr-CA", viewport={"width": 1440, "height": 1100})
        page = await context.new_page()
        try:
            await page.goto(URL, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(3000)

            for phrase in ["Accepter", "Tout accepter", "J’accepte", "J'accepte"]:
                try:
                    btn = page.get_by_role("button", name=re.compile(phrase, re.I))
                    if await btn.count() and await btn.first.is_visible():
                        await btn.first.click(timeout=1500)
                        break
                except Exception:
                    pass

            if city and not await fill_city(page, city):
                raise RuntimeError("Champ Ville introuvable")

            search_candidates = [
                page.get_by_role("button", name=re.compile("rechercher|chercher|search", re.I)),
                page.locator('button:has-text("Rechercher"), button:has-text("Chercher"), input[type="submit"]'),
            ]
            clicked = False
            for locator in search_candidates:
                try:
                    if await locator.count() and await locator.first.is_visible():
                        await locator.first.click(timeout=15000)
                        clicked = True
                        break
                except Exception:
                    pass
            if not clicked:
                await page.keyboard.press("Enter")

            await page.wait_for_timeout(6000)

            try:
                radius_control = page.get_by_text(re.compile(rf"^{radius}\s*km$", re.I)).first
                if await radius_control.count() and await radius_control.is_visible():
                    await radius_control.click(timeout=3000)
                    await page.wait_for_timeout(3000)
            except Exception:
                pass

            last_height = 0
            stable = 0
            for _ in range(80):
                clicked_more = False
                for pattern in [r"voir plus", r"charger plus", r"résultats suivants", r"suivant"]:
                    try:
                        btn = page.get_by_role("button", name=re.compile(pattern, re.I)).first
                        if await btn.count() and await btn.is_visible() and await btn.is_enabled():
                            await btn.click(timeout=2500)
                            await page.wait_for_timeout(1200)
                            clicked_more = True
                            break
                    except Exception:
                        pass
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(900)
                height = await page.evaluate("document.body.scrollHeight")
                stable = stable + 1 if height == last_height and not clicked_more else 0
                last_height = height
                if stable >= 3:
                    break

            records = []
            links = page.locator('a[href^="mailto:"]')
            for i in range(await links.count()):
                link = links.nth(i)
                href = await link.get_attribute("href") or ""
                email = clean(href.split(":", 1)[-1].split("?", 1)[0]).lower()
                if not EMAIL_RE.fullmatch(email):
                    continue
                text = ""
                for xpath in [
                    "xpath=ancestor::*[self::article or self::li][1]",
                    "xpath=ancestor::div[count(.//a[starts-with(@href,'mailto:')])=1][1]",
                    "xpath=ancestor::div[1]",
                ]:
                    try:
                        box = link.locator(xpath)
                        if await box.count():
                            candidate = clean(await box.first.inner_text(timeout=2000))
                            if candidate and len(candidate) < 2500:
                                text = candidate
                                break
                    except Exception:
                        pass
                lines = [clean(x) for x in text.splitlines() if clean(x)]
                phone_match = PHONE_RE.search(text)
                phone = clean(phone_match.group(0)) if phone_match else ""
                useful = [x for x in lines if email not in x.lower() and x != phone]
                records.append({
                    "nom": useful[0] if useful else "",
                    "etude": useful[1] if len(useful) > 1 else "",
                    "courriel": email,
                    "telephone": phone,
                    "adresse": "",
                    "ville": city,
                    "source": page.url,
                })

            deduped = {r["courriel"]: r for r in records}
            rows = sorted(deduped.values(), key=lambda r: (r["nom"].lower(), r["courriel"]))
            out = Path(output)
            with out.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["nom", "etude", "courriel", "telephone", "adresse", "ville", "source"])
                writer.writeheader()
                writer.writerows(rows)

            print(f"Extraction terminée: {len(rows)} courriels uniques -> {output}")
        except Exception:
            await page.screenshot(path="debug-cnq.png", full_page=True)
            Path("debug-cnq.html").write_text(await page.content(), encoding="utf-8")
            raise
        finally:
            await context.close()
            await browser.close()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="Lévis")
    parser.add_argument("--radius", type=int, default=50)
    parser.add_argument("--output", default="notaires_cnq.csv")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main_async(args.city, args.radius, args.output))
