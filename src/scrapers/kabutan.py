from .base import get_soup

URL = "https://kabutan.jp/stock/ranking/?code=0000&market=1&profit=1"


def fetch(top_n: int = 10) -> list[dict]:
    """株探 値上がり率ランキング"""
    soup = get_soup(URL)
    results = []

    for row in soup.select("table.stock_table tbody tr")[:top_n]:
        cols = row.select("td")
        if len(cols) < 5:
            continue

        link = cols[1].find("a")
        name = link.get_text(strip=True) if link else cols[1].get_text(strip=True)
        href = link.get("href", "") if link else ""
        # /stock/?code=7203 → 7203
        code = href.split("code=")[-1].split("&")[0] if "code=" in href else ""
        change = cols[4].get_text(strip=True) if len(cols) > 4 else ""

        results.append({
            "code": code,
            "name": name,
            "change": change,
            "url": "https://kabutan.jp" + href if href.startswith("/") else href,
            "source": "株探",
        })

    return results
