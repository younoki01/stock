"""みんかぶの銘柄ページから目標株価・予想・テクニカル評価を取得する。

対象URL例:
- https://minkabu.jp/stock/7203
- https://minkabu.jp/stock/7203/target
"""

from .base import get_soup


def fetch(code: str) -> dict:
    """みんかぶ銘柄ページから目標株価・予想・評価を抽出。"""
    if not _is_jp_code(code):
        return {"code": code, "source": "minkabu", "supported": False}

    url = f"https://minkabu.jp/stock/{code}"
    try:
        soup = get_soup(url)
    except Exception as e:
        return {"code": code, "source": "minkabu", "url": url, "error": str(e)}

    result: dict = {"code": code, "source": "minkabu", "url": url, "supported": True}

    # 銘柄名
    title = soup.select_one("h1")
    if title:
        result["name"] = title.get_text(strip=True)

    # 目標株価・アナリスト予想（みんかぶ独自評価）
    metric_labels = {
        "個人予想株価": "minkabu_target_individual",
        "アナリスト予想株価": "minkabu_target_analyst",
        "AI株価診断": "minkabu_ai_target",
        "理論株価": "minkabu_theoretical",
        "目標株価": "minkabu_target",
    }

    for box in soup.select("section, div, dl"):
        text = box.get_text(" ", strip=True)
        for label, target in metric_labels.items():
            if label in text and target not in result:
                # ラベル直後の価格らしき値を抽出
                value = _extract_value_near(text, label)
                if value:
                    result[target] = value

    # 短期/中期/長期テクニカル評価（あれば）
    for li in soup.select("li, dt, dd"):
        t = li.get_text(strip=True)
        if "短期" in t and "判定" not in result.get("short_term", ""):
            result.setdefault("short_term", t)
        elif "中期" in t and "判定" not in result.get("medium_term", ""):
            result.setdefault("medium_term", t)
        elif "長期" in t and "判定" not in result.get("long_term", ""):
            result.setdefault("long_term", t)

    return result


def _is_jp_code(code: str) -> bool:
    import re
    return bool(re.match(r"^[0-9][0-9A-Z]{3,4}$", code))


def _extract_value_near(text: str, label: str) -> str:
    """ラベルの後ろから30文字以内で円・数字を含む断片を取得。"""
    idx = text.find(label)
    if idx < 0:
        return ""
    snippet = text[idx + len(label): idx + len(label) + 40]
    return snippet.strip().split()[0] if snippet.strip() else ""
