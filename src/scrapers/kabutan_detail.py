"""株探の銘柄詳細ページから業績・指標を取得する。

対象URL例:
- https://kabutan.jp/stock/?code=7203
- https://kabutan.jp/stock/finance?code=7203
"""

from .base import get_soup


def fetch(code: str) -> dict:
    """株探銘柄ページから主要指標と業績テキストを抽出。

    取得項目:
      name, market, sector, price, change_percent,
      per, pbr, dividend_yield, market_cap, year_high, year_low,
      finance_summary (業績テーブルをテキスト化)
    """
    if not _is_jp_code(code):
        return {"code": code, "source": "kabutan", "supported": False}

    url = f"https://kabutan.jp/stock/?code={code}"
    try:
        soup = get_soup(url)
    except Exception as e:
        return {"code": code, "source": "kabutan", "url": url, "error": str(e)}

    result: dict = {"code": code, "source": "kabutan", "url": url, "supported": True}

    # 銘柄名・市場・業種
    name_el = soup.select_one("div#stockinfo_i1 h2")
    if name_el:
        result["name"] = name_el.get_text(strip=True)

    market_sector = soup.select_one("div#stockinfo_i2")
    if market_sector:
        spans = [s.get_text(strip=True) for s in market_sector.select("span, div") if s.get_text(strip=True)]
        if spans:
            result["market_sector"] = " / ".join(spans[:3])

    # 株価
    price_el = soup.select_one("div#stockinfo_i1 span.kabuka")
    if price_el:
        result["price"] = price_el.get_text(strip=True)

    # 指標テーブル（PER, PBR, 配当利回り, 時価総額, 年初来高値/安値 など）
    metrics = {}
    for th in soup.select("table th"):
        key = th.get_text(strip=True)
        td = th.find_next_sibling("td")
        if not td:
            continue
        val = td.get_text(strip=True)
        if not key or not val:
            continue
        metrics[key] = val

    for label, target in [
        ("PER", "per"),
        ("PBR", "pbr"),
        ("利回り", "dividend_yield"),
        ("時価総額", "market_cap"),
        ("年初来高値", "year_high"),
        ("年初来安値", "year_low"),
        ("予想EPS", "eps_forecast"),
        ("実績PER", "per_actual"),
    ]:
        for k, v in metrics.items():
            if label in k:
                result[target] = v
                break

    # 業績テーブル（決算サマリ）
    finance_table = soup.select_one("table.stock_kabuka_table") or _find_finance_table(soup)
    if finance_table:
        rows_text = []
        for tr in finance_table.select("tr")[:6]:
            cells = [td.get_text(strip=True) for td in tr.select("th, td")]
            if any(cells):
                rows_text.append(" | ".join(cells))
        if rows_text:
            result["finance_summary"] = "\n".join(rows_text)

    return result


def _is_jp_code(code: str) -> bool:
    import re
    return bool(re.match(r"^[0-9][0-9A-Z]{3,4}$", code))


def _find_finance_table(soup):
    # 業績見出しの近くにあるテーブルを探す
    for h in soup.select("h2, h3"):
        if "業績" in h.get_text():
            tbl = h.find_next("table")
            if tbl:
                return tbl
    return None
