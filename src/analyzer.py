import os
import requests
from datetime import datetime, timedelta

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"


def analyze_stock(code: str, days_back: int = 3, model: str = DEFAULT_MODEL) -> dict:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")

    today = datetime.now()
    from_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT%H:%M:%SZ")

    prompt = f"""
{code} についてXの最新投稿を分析してください。

以下の形式で回答してください：

【センチメント】強気 / 中立 / 弱気の割合（例：強気60% 中立30% 弱気10%）
【注目ポイント】
- （投資家が期待しているポイントを最大3つ）
【懸念・リスク】
- （投資家が懸念しているポイントを最大3つ）
【最新材料】
- （直近の決算・ニュース・材料への反応を最大3つ）

日本語で回答してください。
"""

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
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    text = _extract_text(data)
    citations = data.get("citations", [])

    return {
        "code": code,
        "timestamp": today.isoformat(),
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
