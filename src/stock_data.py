"""複数ソースから個別銘柄データを集約する。"""

from src.scrapers.stock_detail import fetch_detail as fetch_yahoo
from src.scrapers.kabutan_detail import fetch as fetch_kabutan
from src.scrapers.minkabu_detail import fetch as fetch_minkabu


def collect(code: str) -> dict:
    """3つのソースから個別銘柄データを収集。失敗したソースはerrorキー付きで返る。"""
    yahoo = _safe(fetch_yahoo, code)
    kabutan = _safe(fetch_kabutan, code)
    minkabu = _safe(fetch_minkabu, code)

    name = yahoo.get("name") or kabutan.get("name") or minkabu.get("name") or ""

    return {
        "code": code,
        "name": name,
        "yahoo": yahoo,
        "kabutan": kabutan,
        "minkabu": minkabu,
    }


def format_for_prompt(data: dict) -> str:
    """LLMプロンプト用に集約データをテキスト化する。"""
    code = data["code"]
    name = data.get("name", "")
    lines = [f"銘柄: {code} {name}".strip()]

    y = data.get("yahoo", {})
    if y.get("price") or y.get("change"):
        lines.append(f"[Yahoo Finance] 株価: {y.get('price', '-')} / 騰落: {y.get('change', '-')}")

    k = data.get("kabutan", {})
    if k.get("supported"):
        kabutan_lines = []
        for label, key in [
            ("市場/業種", "market_sector"),
            ("株価", "price"),
            ("PER", "per"),
            ("PBR", "pbr"),
            ("配当利回り", "dividend_yield"),
            ("時価総額", "market_cap"),
            ("年初来高値", "year_high"),
            ("年初来安値", "year_low"),
        ]:
            if k.get(key):
                kabutan_lines.append(f"  {label}: {k[key]}")
        if kabutan_lines:
            lines.append("[株探]")
            lines.extend(kabutan_lines)
        if k.get("finance_summary"):
            lines.append("[株探-業績]")
            lines.append(k["finance_summary"])

    m = data.get("minkabu", {})
    if m.get("supported"):
        minkabu_lines = []
        for label, key in [
            ("個人予想株価", "minkabu_target_individual"),
            ("アナリスト予想株価", "minkabu_target_analyst"),
            ("AI株価診断", "minkabu_ai_target"),
            ("理論株価", "minkabu_theoretical"),
            ("目標株価", "minkabu_target"),
            ("短期評価", "short_term"),
            ("中期評価", "medium_term"),
            ("長期評価", "long_term"),
        ]:
            if m.get(key):
                minkabu_lines.append(f"  {label}: {m[key]}")
        if minkabu_lines:
            lines.append("[みんかぶ]")
            lines.extend(minkabu_lines)

    errors = [s for s in ("yahoo", "kabutan", "minkabu") if data.get(s, {}).get("error")]
    if errors:
        lines.append(f"(取得失敗: {', '.join(errors)})")

    return "\n".join(lines)


def _safe(fn, code: str) -> dict:
    try:
        return fn(code)
    except Exception as e:
        return {"code": code, "error": str(e)}
