import os
import requests
from datetime import datetime, timedelta

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"

STRATEGY_PROMPT_TEMPLATE = """
以下は本日（{today}）の株式市場分析データです。

【X注目銘柄】
{hot_stocks_text}

【国内値上がりランキング】
{rankings_text}

---
このデータを踏まえ、手元に100万円あった場合の本日の運用戦略を提案してください。

以下の形式で回答してください：

【運用方針】
（リスク許容度：中程度・短期〜中期目線として、今日の市場環境を一言で評価）

【ポートフォリオ案】
| 銘柄コード／銘柄名 | 配分 | 予算 | 狙い |
（最大5銘柄、合計100万円になるように配分）

【エントリーポイント】
- 各銘柄の理想的な買いタイミングや価格帯

【リスク管理】
- 損切りライン・注意すべきリスク要因

【現金比率の考え方】
- キャッシュポジションをどの程度残すべきか

日本語で回答してください。
"""


def generate_strategy(hot_stocks_text: str, rankings_text: str, model: str = DEFAULT_MODEL) -> dict:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")

    today = datetime.now()
    from_date = (today - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT%H:%M:%SZ")

    prompt = STRATEGY_PROMPT_TEMPLATE.format(
        today=today.strftime("%Y/%m/%d"),
        hot_stocks_text=hot_stocks_text or "（データなし）",
        rankings_text=rankings_text or "（データなし）",
    )

    payload = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
        "tools": [{"type": "x_search", "from_date": from_date, "to_date": to_date}],
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

    text = _extract_text(data)

    return {
        "timestamp": today.isoformat(),
        "text": text,
    }


def _extract_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return ""
