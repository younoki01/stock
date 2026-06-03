"""TDnet 適時開示を yanoshin の無料JSONミラー経由で取得する。

上方修正・自社株買い・提携・受注などの「公式の早期材料」を最速で拾う。
スクレイピングではなくJSON APIなので比較的堅牢（第三者ミラーである点は留意）。
"""
import requests

API_TODAY = "https://webapi.yanoshin.jp/webapi/tdnet/list/today.json"
API_RECENT = "https://webapi.yanoshin.jp/webapi/tdnet/list/recent.json"

# 株価インパクトの大きい開示の見出しキーワード → カテゴリ
MATERIAL_KEYWORDS = [
    ("上方修正", "上方修正"),
    ("業績予想の修正", "業績修正"),
    ("通期業績予想", "業績修正"),
    ("自己株式の取得", "自社株買い"),
    ("自己株式取得", "自社株買い"),
    ("増配", "増配"),
    ("配当予想の修正", "配当修正"),
    ("株式分割", "株式分割"),
    ("資本業務提携", "提携"),
    ("業務提携", "提携"),
    ("公開買付", "TOB"),
    ("株式公開買付", "TOB"),
    ("子会社化", "M&A"),
    ("買収", "M&A"),
    ("受注", "受注"),
    ("新製品", "新製品"),
]


def fetch(limit: int = 50, recent: bool = False) -> list[dict]:
    """本日（recent=Trueなら直近）の適時開示を取得。失敗時は空リスト。

    返り値: [{"time", "code", "name", "title", "url"}, ...]
    """
    url = API_RECENT if recent else API_TODAY
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception:
        return []

    out = []
    for it in items:
        t = it.get("Tdnet", it)
        code = (t.get("company_code") or "")[:4]  # 5桁(末尾0)→売買コード4桁
        pub = t.get("pubdate", "") or ""
        out.append({
            "time": pub[11:16],
            "code": code,
            "name": t.get("company_name", ""),
            "title": t.get("title", ""),
            "url": t.get("document_url", "") or t.get("url", ""),
        })
        if len(out) >= limit:
            break
    return out


# 定型の進捗・訂正など、インパクトの小さい見出しは除外
NOISE_KEYWORDS = ["取得状況", "取得結果", "取得終了", "立会外分売", "訂正", "月次"]


def material(items: list[dict]) -> list[dict]:
    """重要キーワードを含む開示だけ抽出し category を付与（最初に一致したもの）。

    定型の進捗報告・訂正（NOISE_KEYWORDS）は除外する。
    """
    res = []
    for it in items:
        title = it.get("title", "")
        if any(n in title for n in NOISE_KEYWORDS):
            continue
        for kw, cat in MATERIAL_KEYWORDS:
            if kw in title:
                res.append({**it, "category": cat})
                break
    return res


def format_for_slack(items: list[dict], limit: int = 12) -> str:
    """重要開示を Slack mrkdwn テキストに整形。空なら空文字。"""
    if not items:
        return ""
    lines = []
    for it in items[:limit]:
        code = f"{it['code']} " if it.get("code") else ""
        lines.append(f"• `{it.get('category','')}` {code}{it.get('name','')}：{it.get('title','')[:48]}")
    return "\n".join(lines)
