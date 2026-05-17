from .base import get_soup

URL = "https://minkabu.jp/stock/ranking/rise"


def fetch(top_n: int = 10) -> list[dict]:
    """みんかぶ 値上がり率ランキング"""
    soup = get_soup(URL)
    results = []

    for row in soup.select("tr.stock_table_tr")[:top_n]:
        cols = row.select("td")
        if len(cols) < 4:
            continue
        link = cols[1].find("a")
        code = cols[1].select_one(".stock_code")
        name = cols[1].select_one(".stock_name") or cols[1].select_one("a")
        change = cols[3].get_text(strip=True) if len(cols) > 3 else ""

        results.append({
            "code": code.get_text(strip=True) if code else "",
            "name": name.get_text(strip=True) if name else "",
            "change": change,
            "url": "https://minkabu.jp" + link["href"] if link and link.get("href") else "",
            "source": "みんかぶ",
        })

    return results
