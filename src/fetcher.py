import os
import requests
from datetime import datetime, timedelta

from src import usage_log


API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"

PROMPT = """
今日のXの投稿から、日本株・米国株の注目銘柄を以下のカテゴリに分けて教えてください。
各銘柄は「銘柄コード／銘柄名：理由」の形式で記載してください。各カテゴリ最大5銘柄。

【日本株】
■ 急騰・急落銘柄
■ 成長株・グロース株
■ 新興・小型株

【米国株】
■ 急騰・急落銘柄
■ 成長株・グロース株
■ テーマ株（AI・半導体・EV など）

カテゴリに該当する銘柄がなければ「なし」と記載してください。
日本語で回答してください。
"""


def fetch_hot_stocks(days_back: int = 1, model: str = DEFAULT_MODEL) -> dict:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")

    today = datetime.now()
    from_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "model": model,
        "input": [{"role": "user", "content": PROMPT}],
        "tools": [
            {
                "type": "x_search",
                "from_date": from_date,
                "to_date": to_date,
            }
        ],
    }

    response = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    usage_log.record("fetcher", model, data)

    text = _extract_text(data)
    citations = data.get("citations", [])

    return {
        "timestamp": today.isoformat(),
        "from_date": from_date,
        "to_date": to_date,
        "text": text,
        "citations": citations,
    }


def _extract_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return ""
