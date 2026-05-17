import re
from .base import get_soup


def fetch_detail(code: str) -> dict:
    """Yahoo Finance Japan から株価・騰落率を取得。JP株は .T を付与。"""
    suffix = ".T" if _is_jp(code) else ""
    url = f"https://finance.yahoo.co.jp/quote/{code}{suffix}"

    try:
        soup = get_soup(url)
        price = _find_text(soup, ["span[data-field='regularMarketPrice']", "._3rXWJKZF"])
        change = _find_text(soup, ["span[data-field='regularMarketChangePercent']", "._1n2YBjFp"])
        name = _find_text(soup, ["h1", "title"])
        return {"code": code, "name": name, "price": price, "change": change, "url": url}
    except Exception as e:
        return {"code": code, "name": "", "price": "", "change": "", "url": url, "error": str(e)}


def _is_jp(code: str) -> bool:
    return bool(re.match(r"^\d{4}$", code))


def _find_text(soup, selectors: list) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            return el.get_text(strip=True)
    return ""
