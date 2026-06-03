"""株探の銘柄ニュースを順次収集し、LLM で「材料ダイジェスト」にまとめる。

Live Search は使わない（スクレイピング済みの見出しテキストを渡すだけ）。
→ 検索ソース課金なし・純トークン代のみで安価。
"""
import os
import re
import requests
from datetime import datetime

from src.scrapers.kabutan_news import fetch as fetch_news

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"
CODE_RE = re.compile(r"^[0-9][0-9A-Z]{3,4}$")

DIGEST_PROMPT_TEMPLATE = """
以下は本日収集した複数銘柄の株探ニュース見出しです。
各銘柄について、株価に影響しうる「材料」を中心に要点を簡潔にまとめてください。

【厳守事項】
- 収集済みの見出しに無い情報を創作しないこと（根拠は下記の見出しのみ）
- 定型の特集・ランキング告知・全体ダイジェスト等のノイズは省き、
  決算・業績修正・受注/提携・格付け・需給イベント等の個別材料を優先
- 各銘柄2行以内。めぼしい材料が無い銘柄は丸ごと省略してよい
- 可能なら強気/弱気のニュアンスを一言添える
- 太字は *単一アスタリスク* で囲む（**二重** は Slack で無効なので禁止）

【収集データ】
{news_block}

【出力形式（Slack mrkdwn）】
*7203 トヨタ自動車*
• 材料の要点（強気/弱気のニュアンス） ／（M/D）

日本語、Slack mrkdwn 形式で回答してください。
"""


def collect_news(codes: list[str], per_stock: int = 6) -> dict[str, list[dict]]:
    """複数銘柄の株探ニュースを順次スクレイピング。見出しがある銘柄のみ返す。"""
    out: dict[str, list[dict]] = {}
    for code in codes:
        if not CODE_RE.match(code):
            continue
        items = fetch_news(code, limit=per_stock)
        if items:
            out[code] = items
    return out


def _format_news_block(news_by_code: dict[str, list[dict]]) -> str:
    lines = []
    for code, items in news_by_code.items():
        lines.append(f"■ {code}")
        for it in items:
            lines.append(f"- {it['datetime']} [{it['category']}] {it['title']}")
    return "\n".join(lines)


def generate_digest(codes: list[str], per_stock: int = 6, model: str = DEFAULT_MODEL) -> dict:
    """順次収集 → LLM 要約。Slack 用テキストと生データを返す。"""
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")

    news_by_code = collect_news(codes, per_stock=per_stock)
    if not news_by_code:
        return {"timestamp": datetime.now().isoformat(), "text": "", "news_by_code": {}}

    prompt = DIGEST_PROMPT_TEMPLATE.format(news_block=_format_news_block(news_by_code))

    # tools 無し = Live Search 課金なしの純 LLM 呼び出し
    payload = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
    }

    response = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()

    return {
        "timestamp": datetime.now().isoformat(),
        "text": _to_slack_mrkdwn(_extract_text(data)),
        "news_by_code": news_by_code,
    }


def _to_slack_mrkdwn(text: str) -> str:
    text = re.sub(r"\*{2,}([^*\n]+?)\*{2,}", r"*\1*", text)
    text = re.sub(r"\*{2,}", "*", text)
    text = re.sub(r"\*[ \t]*\*", "", text)
    return text


def _extract_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return ""
