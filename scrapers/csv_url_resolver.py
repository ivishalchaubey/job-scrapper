import csv
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


CSV_PATH = Path(__file__).resolve().parent.parent / "scrappers.csv"


def _normalize_url(raw_url):
    if not raw_url:
        return ""

    url = raw_url.strip()
    if not url:
        return ""

    if url.startswith("google.com/url?"):
        url = "https://" + url

    parsed = urlparse(url)
    if parsed.netloc.endswith("google.com") and parsed.path == "/url":
        qs = parse_qs(parsed.query)
        q_vals = qs.get("q")
        if q_vals:
            return unquote(q_vals[0]).strip()

    return url


@lru_cache(maxsize=1)
def _load_company_urls():
    company_to_url = {}
    if not CSV_PATH.exists():
        return company_to_url

    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            company = row[0].strip()
            url = _normalize_url(row[1])
            if company and url:
                company_to_url[company.lower()] = url
    return company_to_url


def get_company_url(company_name, fallback_url=""):
    urls = _load_company_urls()
    return urls.get(company_name.lower(), fallback_url)
