"""株探の個別銘柄ニュース一覧を取得する。

対象URL例: https://kabutan.jp/stock/news?code=7203
ニュースは table.s_news_list に「日時 | カテゴリ | 見出し(リンク)」の行で並ぶ。
"""
import re

from .base import get_soup

CODE_RE = re.compile(r"^[0-9][0-9A-Z]{3,4}$")


def fetch(code: str, limit: int = 8) -> list[dict]:
    """株探の個別銘柄ニュース見出しを新しい順に取得。

    返り値: [{"datetime", "category", "title", "url"}, ...]
    日本株コード以外、または取得失敗時は空リストを返す。
    """
    if not CODE_RE.match(code):
        return []

    url = f"https://kabutan.jp/stock/news?code={code}"
    try:
        soup = get_soup(url)
    except Exception:
        return []

    items: list[dict] = []
    for tr in soup.select("table.s_news_list tr"):
        cells = tr.find_all("td")
        if len(cells) < 3:
            continue
        dt = cells[0].get_text(strip=True)
        category = cells[1].get_text(strip=True)
        link = cells[2].find("a")
        title = link.get_text(strip=True) if link else cells[2].get_text(strip=True)
        if not title:
            continue
        href = link.get("href", "") if link else ""
        items.append({
            "datetime": dt,
            "category": category,
            "title": title,
            "url": "https://kabutan.jp" + href if href.startswith("/") else href,
        })
        if len(items) >= limit:
            break

    return items
