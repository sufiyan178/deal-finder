import json
import math
import os
import re
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from curl_cffi import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import Client, create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="BuyHatke Clone API", version="4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProductRequest(BaseModel):
    url: str
    user_id: str | None = "guest"


def normalize_url(url: str) -> str:
    """Strips tracking parameters while keeping valid Amazon & Flipkart URL structures."""
    clean = url.strip()
    if not re.match(r"^https?://", clean, re.IGNORECASE):
        clean = f"https://{clean}"

    lower_url = clean.lower()
    if "amazon." in lower_url:
        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", clean, re.IGNORECASE)
        if match:
            domain = "amazon.com" if "amazon.com" in lower_url else "amazon.in"
            return f"https://www.{domain}/dp/{match.group(1).upper()}"
    elif "flipkart.com" in lower_url:
        match = re.search(
            r"(https?://(?:www\.)?flipkart\.com/[^?#]+/p/[a-zA-Z0-9]+)",
            clean,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return clean.split("?")[0]
    return clean


def extract_key_specs(title: str) -> dict[str, set[str]]:
    t = title.lower()
    cpu_patterns = [
        r"\bi[3579][-\s]?\d{4,5}[a-z]*\b",
        r"\bcore\s*ultra\s*[579]\b",
        r"\bryzen\s*[3579]\s*\d{4}[a-z]*\b",
        r"\bryzen\s*[3579]\b",
        r"\bm[1234]\s*(?:pro|max)?\b",
        r"\bsnapdragon\s*[a-z0-9+]+\b",
        r"\bdimensity\s*\d+\b",
    ]
    cpus: set[str] = set()
    for pat in cpu_patterns:
        for m in re.findall(pat, t):
            cpus.add(re.sub(r"\s+", " ", m.strip()))

    mem_tokens = set(re.findall(r"\b(?:4|6|8|12|16|24|32|64)\s*gb\b", t))
    storage_tokens = set(re.findall(r"\b(?:128|256|512)\s*gb|\b[124]\s*tb\b", t))
    gpus = set(re.findall(r"\brtx\s*\d{4}\b|\bgtx\s*\d{4}\b", t))

    return {
        "cpus": {re.sub(r"\s+", "", c) for c in cpus},
        "mem": {re.sub(r"\s+", "", m) for m in mem_tokens},
        "storage": {re.sub(r"\s+", "", s) for s in storage_tokens},
        "gpus": {re.sub(r"\s+", "", g) for g in gpus},
    }


def is_exact_product_match(source_title: str, candidate_title: str) -> tuple[bool, float]:
    src_specs = extract_key_specs(source_title)
    cand_specs = extract_key_specs(candidate_title)

    if src_specs["cpus"] and cand_specs["cpus"]:
        cpu_overlap = False
        for sc in src_specs["cpus"]:
            for cc in cand_specs["cpus"]:
                if sc == cc or sc in cc or cc in sc:
                    cpu_overlap = True
                    break
        if not cpu_overlap:
            return False, 0.0

    if src_specs["gpus"] and cand_specs["gpus"]:
        if not (src_specs["gpus"] & cand_specs["gpus"]):
            return False, 0.0

    if src_specs["storage"] and cand_specs["storage"]:
        if not (src_specs["storage"] & cand_specs["storage"]):
            return False, 0.0

    clean_src = re.sub(r"[^a-z0-9\s]", " ", source_title.lower())
    clean_cand = re.sub(r"[^a-z0-9\s]", " ", candidate_title.lower())

    stop_words = {
        "with", "and", "for", "the", "laptop", "gaming", "inch", "cm", "fhd",
        "windows", "win", "home", "office", "black", "grey", "silver", "blue",
        "ram", "ssd", "ddr4", "ddr5", "144hz", "165hz", "15", "16", "14",
    }
    src_tokens = [w for w in clean_src.split()[:10] if len(w) > 1 and w not in stop_words]
    cand_token_set = set(clean_cand.split())

    if not src_tokens:
        return False, 0.0

    matched = sum(1 for tok in src_tokens if tok in cand_token_set)
    ratio = matched / len(src_tokens)

    if ratio < 0.6:
        return False, round(ratio, 3)

    return True, round(ratio, 3)


def build_compact_search_query(title: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", " ", title)
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", " ", cleaned)
    words = [w for w in cleaned.split() if len(w) > 1]
    return " ".join(words[:7])


def compute_title_relevance(title: str, query: str) -> float:
    clean_title = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    clean_query = re.sub(r"[^a-z0-9\s]", " ", query.lower()).strip()

    if not clean_query:
        return 1.0

    query_tokens = [tok for tok in clean_query.split() if len(tok) > 1]
    if not query_tokens:
        query_tokens = clean_query.split()

    title_tokens = set(clean_title.split())
    matched_tokens = sum(1 for tok in query_tokens if tok in title_tokens)
    token_ratio = matched_tokens / max(len(query_tokens), 1)

    exact_phrase_bonus = 0.25 if clean_query in " ".join(clean_title.split()) else 0.0
    early_title = " ".join(clean_title.split()[:8])
    early_matches = sum(1 for tok in query_tokens if tok in early_title)
    early_bonus = 0.15 * (early_matches / max(len(query_tokens), 1))

    return round(min(token_ratio + exact_phrase_bonus + early_bonus, 1.4), 3)


def compute_deal_score(
    title: str,
    query: str,
    price: float,
    mrp: float | None,
    rating: float,
    reviews: int,
    avg_price: float,
) -> tuple[float, float]:
    if price <= 0:
        return 0.0, 0.0

    relevance = compute_title_relevance(title, query)
    price_ratio = min(avg_price / price, 2.0) if avg_price > 0 else 1.0
    rating_factor = max(min(rating / 5.0, 1.0), 0.2)
    trust_factor = 1.0 + (math.log10(max(reviews, 0) + 1) / 5.0)

    discount_bonus = 1.0
    if mrp and mrp > price:
        discount_pct = min((mrp - price) / mrp, 0.6)
        discount_bonus += discount_pct * 0.5

    relevance_weight = max(relevance, 0.15) ** 2
    score = relevance_weight * price_ratio * (rating_factor**1.5) * trust_factor * discount_bonus
    return round(score * 100, 2), relevance


def _fetch_amazon_html(url: str) -> tuple[str | None, str]:
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.in/",
        "Upgrade-Insecure-Requests": "1",
    }
    last_status = "unknown"
    for attempt in range(2):
        try:
            resp = requests.get(
                url,
                headers=headers,
                impersonate="chrome",
                allow_redirects=True,
                timeout=15,
            )
            last_status = str(resp.status_code)
            if resp.status_code == 200:
                lower = resp.text.lower()
                if "enter the characters you see below" in lower or "api-services-support@amazon.com" in lower:
                    last_status = "CAPTCHA"
                else:
                    return resp.text, "OK"
        except Exception as exc:
            last_status = str(exc)

        if attempt == 0:
            time.sleep(1.2)

    return None, f"Amazon status {last_status}"


def scrape_amazon_search(query: str, fetch_limit: int = 15) -> tuple[list[dict], str]:
    search_url = f"https://www.amazon.in/s?k={quote_plus(query)}"
    html, status_msg = _fetch_amazon_html(search_url)
    if not html:
        return [], status_msg

    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    cards = soup.select("div[data-component-type='s-search-result']")
    if not cards:
        cards = soup.select("div.s-result-item[data-asin]")

    for card in cards:
        asin = card.get("data-asin", "").strip()
        if not asin:
            continue

        title = ""
        for sel in [
            "h2 a span",
            "h2 span.a-text-normal",
            "h2 span",
            "h2",
            "a.a-link-normal.s-line-clamp-2 span",
            "a.a-link-normal.s-line-clamp-3 span",
            "a.a-link-normal.s-line-clamp-4 span",
        ]:
            el = card.select_one(sel)
            if el:
                txt = el.get_text(" ", strip=True)
                if len(txt) > 5 and not txt.lower().startswith("sponsored"):
                    title = txt
                    break

        if not title:
            img_el = card.select_one("img.s-image")
            if img_el and img_el.get("alt"):
                alt_txt = img_el["alt"].strip()
                if len(alt_txt) > 5:
                    title = re.sub(r"^Sponsored Ad\s*-\s*", "", alt_txt, flags=re.IGNORECASE)

        if not title:
            continue

        price = 0.0
        for p_sel in [
            ".a-price:not(.a-text-price) .a-offscreen",
            ".a-price .a-price-whole",
            "span.a-price-whole",
        ]:
            p_el = card.select_one(p_sel)
            if p_el:
                p_clean = re.sub(r"[^\d.]", "", p_el.get_text(strip=True))
                if p_clean:
                    val = float(p_clean)
                    if val > 0:
                        price = val
                        break

        if price <= 0:
            continue

        mrp = None
        mrp_el = card.select_one(".a-price.a-text-price .a-offscreen")
        if mrp_el:
            mrp_clean = re.sub(r"[^\d.]", "", mrp_el.get_text(strip=True))
            if mrp_clean:
                mrp = float(mrp_clean)

        rating = 4.0
        rating_el = card.select_one("span.a-icon-alt")
        if rating_el:
            m = re.search(r"([\d.]+)", rating_el.get_text())
            if m:
                rating = float(m.group(1))

        reviews = 0
        reviews_el = card.select_one(
            "span[aria-label$='ratings'], span.a-size-base.s-underline-text"
        )
        if reviews_el:
            rev_clean = re.sub(r"[^\d]", "", reviews_el.get_text(strip=True))
            if rev_clean:
                reviews = int(rev_clean)

        link_el = card.select_one("h2 a") or card.select_one("a.a-link-normal[href*='/dp/']")
        href = link_el.get("href") if link_el else ""
        full_url = f"https://www.amazon.in{href}" if href and href.startswith("/") else (href or "")
        clean_url = normalize_url(full_url) if full_url else ""
        if (not clean_url or "/dp/" not in clean_url) and re.match(r"^[A-Z0-9]{10}$", asin):
            clean_url = f"https://www.amazon.in/dp/{asin}"

        if not clean_url:
            continue

        img_el = card.select_one("img.s-image")
        items.append(
            {
                "title": title,
                "store": "amazon",
                "price": price,
                "mrp": mrp,
                "rating": rating,
                "reviews": reviews,
                "url": clean_url,
                "image_url": img_el.get("src") if img_el else None,
            }
        )

        if len(items) >= fetch_limit:
            break

    return items, f"Amazon parsed {len(items)} items"


def scrape_flipkart_search(query: str, fetch_limit: int = 15) -> tuple[list[dict], str]:
    search_url = f"https://www.flipkart.com/search?q={quote_plus(query)}&marketplace=FLIPKART"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.flipkart.com/",
    }
    try:
        resp = requests.get(
            search_url,
            headers=headers,
            impersonate="chrome",
            timeout=15,
        )
    except Exception as exc:
        return [], f"Flipkart request error: {exc}"

    if resp.status_code != 200:
        return [], f"Flipkart status {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    items: list[dict] = []
    seen_hrefs: set[str] = set()

    for link_el in soup.select("a[href*='/p/']"):
        href = link_el.get("href", "")
        if not href or href in seen_hrefs:
            continue

        card = link_el
        for _ in range(5):
            if card.parent and card.parent.name == "div":
                card = card.parent
                if card.get("data-id") or "₹" in card.get_text():
                    break

        title_el = (
            card.select_one("div.KzDlHZ")
            or card.select_one("a.wjcEIp")
            or card.select_one("div._4rR01T")
            or card.select_one("a[title]")
        )
        title = ""
        if title_el:
            title = title_el.get("title") or title_el.get_text(strip=True)
        if not title or len(title) < 4:
            img_alt = card.select_one("img[alt]")
            if img_alt:
                title = img_alt.get("alt", "").strip()
        if not title or len(title) < 4:
            continue

        card_text = card.get_text(" ", strip=True)
        rupee_matches = re.findall(r"₹\s*([\d,]+)", card_text)
        if not rupee_matches:
            continue

        prices = [float(p.replace(",", "")) for p in rupee_matches if p.replace(",", "").isdigit()]
        prices = [p for p in prices if p > 0]
        if not prices:
            continue

        price = prices[0]
        mrp = prices[1] if len(prices) > 1 and prices[1] > price else None

        rating = 4.0
        rating_el = card.select_one("div.XQDdHH") or card.select_one("div._3LWZlK")
        if rating_el:
            m = re.search(r"([\d.]+)", rating_el.get_text())
            if m:
                rating = float(m.group(1))

        reviews = 0
        rev_match = re.search(r"([\d,]+)\s*Ratings", card_text, re.IGNORECASE)
        if rev_match:
            reviews = int(rev_match.group(1).replace(",", ""))

        img_el = card.select_one("img")
        full_url = f"https://www.flipkart.com{href}" if href.startswith("/") else href
        clean_url = normalize_url(full_url)
        seen_hrefs.add(href)

        items.append(
            {
                "title": title,
                "store": "flipkart",
                "price": price,
                "mrp": mrp,
                "rating": rating,
                "reviews": reviews,
                "url": clean_url,
                "image_url": img_el.get("src") if img_el else None,
            }
        )

        if len(items) >= fetch_limit:
            break

    return items, f"Flipkart parsed {len(items)} items"


def scrape_single_page(raw_url: str) -> dict:
    url = normalize_url(raw_url)
    lower_url = url.lower()

    if not any(host in lower_url for host in ("amazon.", "amzn.in", "flipkart.com")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported URL. Please paste a valid Amazon or Flipkart product link.",
        )

    referer = "https://www.flipkart.com/" if "flipkart" in lower_url else "https://www.amazon.in/"
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": referer,
        "Upgrade-Insecure-Requests": "1",
    }

    response = None
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                headers=headers,
                impersonate="chrome",
                allow_redirects=True,
                timeout=15,
            )
        except Exception as exc:
            if attempt == 1:
                raise HTTPException(
                    status_code=502,
                    detail=f"Network error while reaching store: {exc}",
                )
            time.sleep(1.5)
            continue

        if response.status_code == 200:
            break
        if response.status_code in (429, 503) and attempt == 0:
            time.sleep(1.5)
            continue
        break

    if response is None or response.status_code != 200:
        code = response.status_code if response is not None else "No Response"
        raise HTTPException(
            status_code=502,
            detail=f"Store blocked or failed to load page (HTTP {code}). Try again in a few seconds.",
        )

    final_url = normalize_url(str(response.url))
    html_lower = response.text.lower()

    if "enter the characters you see below" in html_lower or "api-services-support@amazon.com" in html_lower:
        raise HTTPException(
            status_code=503,
            detail="Amazon temporarily served a CAPTCHA check. Wait a moment and retry.",
        )

    soup = BeautifulSoup(response.text, "html.parser")

    title = "Unknown Product"
    price = 0.0
    mrp = None
    rating = 4.5
    reviews = 0
    image_url = None
    store_name = "unknown"

    if "amazon." in final_url.lower():
        store_name = "amazon"
        title_el = (
            soup.select_one("#productTitle")
            or soup.select_one("h1#title span")
            or soup.select_one("h1 span")
        )
        if title_el:
            title = title_el.get_text(strip=True)

        price_el = (
            soup.select_one("#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen")
            or soup.select_one("#corePrice_feature_div .a-price:not(.a-text-price) .a-offscreen")
            or soup.select_one(".apexPriceToPay .a-offscreen")
            or soup.select_one("#corePriceDisplay_desktop_feature_div .a-price-whole")
            or soup.select_one("#corePrice_feature_div .a-price-whole")
            or soup.select_one(".a-price:not(.a-text-price) .a-offscreen")
            or soup.select_one(".a-price-whole")
        )
        if price_el:
            price_text = re.sub(r"[^\d.]", "", price_el.get_text(strip=True))
            if price_text:
                price = float(price_text)

        mrp_el = soup.select_one(".a-price.a-text-price .a-offscreen")
        if mrp_el:
            mrp_text = re.sub(r"[^\d.]", "", mrp_el.get_text(strip=True))
            if mrp_text:
                mrp = float(mrp_text)

        img_el = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
        if img_el:
            image_url = img_el.get("src")

        rating_el = soup.select_one("span.a-icon-alt")
        if rating_el:
            rating_match = re.search(r"([\d.]+)", rating_el.get_text())
            if rating_match:
                rating = float(rating_match.group(1))

        rev_el = soup.select_one("#acrCustomerReviewText")
        if rev_el:
            rev_text = re.sub(r"[^\d]", "", rev_el.get_text())
            if rev_text:
                reviews = int(rev_text)

    elif "flipkart.com" in final_url.lower():
        store_name = "flipkart"

        for script in soup.select('script[type="application/ld+json"]'):
            try:
                raw_json = json.loads(script.string or "")
                entries = raw_json if isinstance(raw_json, list) else [raw_json]
                for entry in entries:
                    if isinstance(entry, dict) and entry.get("@type") == "Product":
                        if entry.get("name"):
                            title = str(entry["name"]).strip()
                        offers = entry.get("offers")
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict) and offers.get("price"):
                            price = float(str(offers["price"]).replace(",", ""))
                        img_val = entry.get("image")
                        if isinstance(img_val, list) and img_val:
                            image_url = img_val[0]
                        elif isinstance(img_val, str):
                            image_url = img_val
                        agg = entry.get("aggregateRating")
                        if isinstance(agg, dict) and agg.get("ratingValue"):
                            rating = float(agg["ratingValue"])
                        if isinstance(agg, dict) and agg.get("reviewCount"):
                            reviews = int(agg["reviewCount"])
                        break
            except Exception:
                continue

        if title == "Unknown Product":
            title_el = (
                soup.select_one("span.VU-ZEz")
                or soup.select_one("span.B_NuCI")
                or soup.select_one("h1._6EBuvT")
                or soup.select_one("h1 span")
                or soup.select_one("h1")
            )
            if title_el and len(title_el.get_text(strip=True)) > 3:
                title = title_el.get_text(strip=True)
            else:
                og_title = soup.select_one('meta[property="og:title"]')
                if og_title and og_title.get("content"):
                    title = re.sub(
                        r"\s*[-|:]\s*Buy.*$", "", og_title["content"], flags=re.IGNORECASE
                    ).strip()
                elif soup.title and soup.title.string:
                    title = re.sub(
                        r"\s*[-|:]\s*Buy.*$", "", soup.title.string, flags=re.IGNORECASE
                    ).strip()

        if price == 0.0:
            price_el = (
                soup.select_one("div.Nx9bqj.CxhGGd")
                or soup.select_one("div.Nx9bqj")
                or soup.select_one("div._30jeq3")
            )
            if price_el:
                price_text = re.sub(r"[^\d.]", "", price_el.get_text(strip=True))
                if price_text:
                    price = float(price_text)
            else:
                for match in re.finditer(r"₹\s*([\d,]{3,9})", soup.get_text(" ", strip=True)):
                    val = float(match.group(1).replace(",", ""))
                    if val >= 200:
                        price = val
                        break

        if not image_url:
            img_el = (
                soup.select_one("img.DByuf4")
                or soup.select_one("img._396cs4")
                or soup.select_one('meta[property="og:image"]')
            )
            if img_el:
                image_url = img_el.get("src") or img_el.get("content")

    if price == 0.0 or title == "Unknown Product":
        raise HTTPException(
            status_code=422,
            detail=f"Loaded {store_name} page, but could not extract title/price. Make sure it is a direct product page.",
        )

    return {
        "title": title,
        "store": store_name,
        "url": final_url,
        "price": price,
        "mrp": mrp,
        "rating": rating,
        "reviews": reviews,
        "image_url": image_url,
    }


def upsert_listing_in_db(
    product_id: str | None,
    title: str,
    store_name: str,
    url: str,
    price: float,
    image_url: str | None,
    user_id: str = "guest",
) -> tuple[str, str, str]:
    existing_listing = (
        supabase.table("store_listings").select("*").eq("product_url", url).execute()
    )

    if existing_listing.data and len(existing_listing.data) > 0:
        listing = existing_listing.data[0]
        listing_id = listing["id"]
        resolved_product_id = product_id or listing["product_id"]

        supabase.table("store_listings").update(
            {
                "product_id": resolved_product_id,
                "current_price": price,
                "in_stock": True,
            }
        ).eq("id", listing_id).execute()

        supabase.table("price_history").insert(
            {"listing_id": listing_id, "price": price}
        ).execute()

        return resolved_product_id, listing_id, "updated_existing"

    if not product_id:
        product_res = (
            supabase.table("products")
            .insert(
                {
                    "name": title,
                    "category": "Electronics",
                    "image_url": image_url,
                    "user_id": user_id or "guest",
                }
            )
            .execute()
        )
        product_id = product_res.data[0]["id"]

    listing_res = (
        supabase.table("store_listings")
        .insert(
            {
                "product_id": product_id,
                "store_name": store_name,
                "product_url": url,
                "current_price": price,
                "in_stock": True,
            }
        )
        .execute()
    )
    listing_id = listing_res.data[0]["id"]

    supabase.table("price_history").insert(
        {"listing_id": listing_id, "price": price}
    ).execute()

    return product_id, listing_id, "created_new"


@app.post("/compare-url")
def compare_product_url(data: ProductRequest):
    """Scrapes a pasted product URL and compares matching listings across Amazon & Flipkart without saving to DB."""
    primary = scrape_single_page(data.url)
    compact_query = build_compact_search_query(primary["title"])

    amazon_candidates, amz_msg = scrape_amazon_search(compact_query, fetch_limit=12)
    flipkart_candidates, flk_msg = scrape_flipkart_search(compact_query, fetch_limit=12)

    matched_listings: list[dict] = [primary]
    seen_urls = {primary["url"]}

    for cand in amazon_candidates + flipkart_candidates:
        if cand["url"] in seen_urls:
            continue
        is_match, _ = is_exact_product_match(primary["title"], cand["title"])
        if is_match:
            seen_urls.add(cand["url"])
            matched_listings.append(cand)

    avg_price = sum(x["price"] for x in matched_listings) / len(matched_listings)
    for item in matched_listings:
        score, rel = compute_deal_score(
            title=item["title"],
            query=compact_query,
            price=item["price"],
            mrp=item.get("mrp"),
            rating=item.get("rating", 4.0),
            reviews=item.get("reviews", 0),
            avg_price=avg_price,
        )
        item["deal_score"] = score
        item["relevance_score"] = rel

    matched_listings.sort(key=lambda x: x["price"])

    amazon_count = sum(1 for x in matched_listings if x["store"] == "amazon")
    flipkart_count = sum(1 for x in matched_listings if x["store"] == "flipkart")

    return {
        "status": "success",
        "query": primary["title"],
        "count": len(matched_listings),
        "amazon_count": amazon_count,
        "flipkart_count": flipkart_count,
        "average_price": round(avg_price, 2),
        "best_deal": matched_listings[0] if matched_listings else None,
        "results": matched_listings,
        "diagnostics": [amz_msg, flk_msg],
    }


@app.post("/track")
def track_and_compare_url(data: ProductRequest):
    user_id = data.user_id or "guest"
    primary = scrape_single_page(data.url)
    compact_query = build_compact_search_query(primary["title"])

    amazon_candidates, amz_msg = scrape_amazon_search(compact_query, fetch_limit=12)
    flipkart_candidates, flk_msg = scrape_flipkart_search(compact_query, fetch_limit=12)

    matched_listings: list[dict] = [
        {
            **primary,
            "match_score": 1.0,
            "is_source_url": True,
        }
    ]
    seen_urls = {primary["url"]}

    for cand in amazon_candidates + flipkart_candidates:
        if cand["url"] in seen_urls:
            continue
        is_match, match_ratio = is_exact_product_match(primary["title"], cand["title"])
        if is_match:
            seen_urls.add(cand["url"])
            matched_listings.append(
                {
                    **cand,
                    "match_score": match_ratio,
                    "is_source_url": False,
                }
            )

    try:
        product_id, _, action_type = upsert_listing_in_db(
            product_id=None,
            title=primary["title"],
            store_name=primary["store"],
            url=primary["url"],
            price=primary["price"],
            image_url=primary["image_url"],
            user_id=user_id,
        )

        for item in matched_listings:
            if item["url"] == primary["url"]:
                continue
            upsert_listing_in_db(
                product_id=product_id,
                title=item["title"],
                store_name=item["store"],
                url=item["url"],
                price=item["price"],
                image_url=item.get("image_url"),
                user_id=user_id,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    avg_price = sum(x["price"] for x in matched_listings) / len(matched_listings)
    for item in matched_listings:
        score, _ = compute_deal_score(
            title=item["title"],
            query=compact_query,
            price=item["price"],
            mrp=item.get("mrp"),
            rating=item.get("rating", 4.0),
            reviews=item.get("reviews", 0),
            avg_price=avg_price,
        )
        item["deal_score"] = score

    matched_listings.sort(key=lambda x: x["price"])

    stores_found = sorted({x["store"] for x in matched_listings})
    missing_store = None
    if "amazon" not in stores_found:
        missing_store = "amazon"
    elif "flipkart" not in stores_found:
        missing_store = "flipkart"

    return {
        "message": "Product tracked and compared across stores!",
        "data": {
            "status": "success",
            "action": action_type,
            "product_id": product_id,
            "title": primary["title"],
            "price": primary["price"],
            "store": primary["store"],
            "best_offer": matched_listings[0],
            "compared_listings": matched_listings,
            "stores_found": stores_found,
            "missing_store": missing_store,
            "diagnostics": [amz_msg, flk_msg],
        },
    }


@app.get("/search")
def search_and_rank(q: str = Query(..., min_length=2), per_store: int = 5):
    try:
        amazon_raw, amz_msg = scrape_amazon_search(q, fetch_limit=15)
        flipkart_raw, flk_msg = scrape_flipkart_search(q, fetch_limit=15)

        def clean_items(items: list[dict]) -> list[dict]:
            seen: set[str] = set()
            out: list[dict] = []
            for it in items:
                if it["url"] not in seen:
                    seen.add(it["url"])
                    out.append(it)
            return out

        amazon_clean = clean_items(amazon_raw)
        flipkart_clean = clean_items(flipkart_raw)
        combined_pool = amazon_clean + flipkart_clean

        if not combined_pool:
            return {
                "status": "success",
                "query": q,
                "count": 0,
                "amazon_count": 0,
                "flipkart_count": 0,
                "average_price": 0,
                "best_deal": None,
                "results": [],
                "diagnostics": [amz_msg, flk_msg],
            }

        avg_price = sum(item["price"] for item in combined_pool) / len(combined_pool)

        for item in amazon_clean:
            score, rel = compute_deal_score(
                title=item["title"],
                query=q,
                price=item["price"],
                mrp=item["mrp"],
                rating=item["rating"],
                reviews=item["reviews"],
                avg_price=avg_price,
            )
            item["deal_score"] = score
            item["relevance_score"] = rel

        for item in flipkart_clean:
            score, rel = compute_deal_score(
                title=item["title"],
                query=q,
                price=item["price"],
                mrp=item["mrp"],
                rating=item["rating"],
                reviews=item["reviews"],
                avg_price=avg_price,
            )
            item["deal_score"] = score
            item["relevance_score"] = rel

        amazon_clean.sort(key=lambda x: (x["relevance_score"], x["deal_score"]), reverse=True)
        flipkart_clean.sort(key=lambda x: (x["relevance_score"], x["deal_score"]), reverse=True)

        top_amazon = amazon_clean[:per_store]
        top_flipkart = flipkart_clean[:per_store]

        balanced_results = top_amazon + top_flipkart
        balanced_results.sort(key=lambda x: x["price"])

        return {
            "status": "success",
            "query": q,
            "count": len(balanced_results),
            "amazon_count": len(top_amazon),
            "flipkart_count": len(top_flipkart),
            "average_price": round(avg_price, 2),
            "best_deal": balanced_results[0] if balanced_results else None,
            "results": balanced_results,
            "diagnostics": [
                f"{amz_msg} (showing top {len(top_amazon)})",
                f"{flk_msg} (showing top {len(top_flipkart)})",
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/products/{product_id}")
def delete_tracked_product(product_id: str):
    try:
        listings_res = (
            supabase.table("store_listings")
            .select("id")
            .eq("product_id", product_id)
            .execute()
        )
        listing_ids = [row["id"] for row in (listings_res.data or [])]

        if listing_ids:
            supabase.table("price_history").delete().in_("listing_id", listing_ids).execute()
            supabase.table("store_listings").delete().eq("product_id", product_id).execute()

        supabase.table("products").delete().eq("id", product_id).execute()

        return {"status": "success", "deleted_product_id": product_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete product: {str(e)}")


@app.post("/refresh-prices")
def refresh_all_prices(user_id: str | None = None):
    try:
        if user_id:
            prod_res = supabase.table("products").select("id").eq("user_id", user_id).execute()
            prod_ids = [p["id"] for p in (prod_res.data or [])]
            if not prod_ids:
                return {"status": "success", "refreshed_count": 0, "details": []}
            res = supabase.table("store_listings").select("*").in_("product_id", prod_ids).execute()
        else:
            res = supabase.table("store_listings").select("*").execute()

        listings = res.data or []
        updated = []

        for listing in listings:
            url = listing.get("product_url")
            if not url:
                continue
            try:
                scraped = scrape_single_page(url)
                upsert_listing_in_db(
                    product_id=listing.get("product_id"),
                    title=scraped["title"],
                    store_name=scraped["store"],
                    url=scraped["url"],
                    price=scraped["price"],
                    image_url=scraped.get("image_url"),
                    user_id=user_id or "guest",
                )
                updated.append(
                    {
                        "listing_id": listing["id"],
                        "price": scraped["price"],
                        "status": "updated",
                    }
                )
            except Exception as err:
                updated.append(
                    {
                        "listing_id": listing["id"],
                        "status": "failed",
                        "error": str(err),
                    }
                )

        return {
            "status": "success",
            "refreshed_count": len(updated),
            "details": updated,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/products")
def get_products(user_id: str | None = None):
    try:
        query = supabase.table("products").select("*, store_listings(*, price_history(*))")
        if user_id:
            query = query.eq("user_id", user_id)
        res = query.execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {"message": "BuyHatke Backend is running!"}