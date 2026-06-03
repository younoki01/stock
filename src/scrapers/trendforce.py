"""TrendForce のニュース見出しを取得する（上流シグナル源）。

メモリ(DRAM/NAND)スポット価格、供給逼迫、HBM、半導体動向など
「株価に織り込まれる前の業界シグナル」を見出しレベルで収集する。
対象URL: https://www.trendforce.com/news/
"""
import re

from .base import get_soup

URL = "https://www.trendforce.com/news/"
TAG_RE = re.compile(r"^\[(News|Insights|Press Release|Report)\]\s*", re.I)


def fetch(limit: int = 15) -> list[dict]:
    """TrendForce のニュース見出しを取得。

    返り値: [{"tag", "title", "url"}, ...]
    取得失敗時は空リスト。
    """
    try:
        soup = get_soup(URL)
    except Exception:
        return []

    items: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("a[href*='/news/']"):
        title = a.get_text(strip=True)
        if len(title) < 20:
            continue
        href = a.get("href", "")
        if href in seen:
            continue
        seen.add(href)

        m = TAG_RE.match(title)
        tag = m.group(1) if m else ""
        clean = TAG_RE.sub("", title)
        # タグ無しの短い項目はカテゴリ/ナビリンクとみなし除外
        if not tag and len(clean) < 40:
            continue
        items.append({
            "tag": tag,
            "title": clean,
            "url": href if href.startswith("http") else "https://www.trendforce.com" + href,
        })
        if len(items) >= limit:
            break

    return items
