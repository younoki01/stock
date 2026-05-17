from .base import get_soup

URL = "https://finance.yahoo.co.jp/stocks/ranking/up?market=all&term=1d"


def fetch(top_n: int = 10) -> list[dict]:
    """Yahoo Finance Japan 値上がり率ランキング"""
    soup = get_soup(URL)
    results = []

    for row in soup.select("tr")[:top_n + 5]:
        link = row.select_one("a[href*='/quote/']")
        if not link:
            continue

        name = link.get_text(strip=True)
        href = link.get("href", "")
        # /quote/9444.T → 9444
        code = href.split("/quote/")[-1].split(".")[0] if "/quote/" in href else ""

        tds = row.select("td")
        change = ""
        for td in tds:
            text = td.get_text(strip=True)
            if "%" in text and ("+" in text or "-" in text or "－" in text):
                change = text
                break

        if name and code:
            results.append({
                "code": code,
                "name": name,
                "change": change,
                "url": f"https://finance.yahoo.co.jp/quote/{code}.T",
                "source": "Yahoo Finance",
            })
        if len(results) >= top_n:
            break

    return results
