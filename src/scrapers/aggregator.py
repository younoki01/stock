from . import minkabu, yahoo_finance, kabutan


SCRAPERS = [
    ("みんかぶ", minkabu.fetch),
    ("Yahoo Finance", yahoo_finance.fetch),
    ("株探", kabutan.fetch),
]


def fetch_all_rankings(top_n: int = 10) -> dict[str, list[dict]]:
    """全サイトから値上がり率ランキングを取得。失敗したサイトはスキップ。"""
    results = {}
    for name, fn in SCRAPERS:
        try:
            results[name] = fn(top_n=top_n)
        except Exception as e:
            results[name] = [{"error": str(e)}]
    return results


def format_rankings(rankings: dict[str, list[dict]]) -> str:
    lines = []
    for source, stocks in rankings.items():
        lines.append(f"*【{source} 値上がりランキング TOP10】*")
        if not stocks:
            lines.append("  データなし")
        elif "error" in stocks[0]:
            lines.append(f"  取得失敗: {stocks[0]['error']}")
        else:
            for i, s in enumerate(stocks, 1):
                change = f"  {s['change']}" if s.get("change") else ""
                lines.append(f"  {i}. {s['code']} {s['name']}{change}")
        lines.append("")
    return "\n".join(lines).strip()
