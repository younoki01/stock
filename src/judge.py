"""集約された銘柄データを元に Grok で買い判定を行う。"""

import os
import requests
from datetime import datetime, timedelta

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"

JUDGE_PROMPT_TEMPLATE = """
以下の個別銘柄データと、Xの最新投稿（直近 {days_back} 日分）を踏まえて、
短期〜中期目線で「買いか / 中立か / 売りか」を判定してください。

【集約データ】
{aggregated}

---

以下のフォーマットで日本語で回答してください。文字数は全体で1500字以内。

【判定】買い / 中立 / 売り（いずれか1つ）
【確信度】★☆☆〜★★★ で表示（3段階）
【根拠（強気材料）】
- （箇条書きで最大3件、業績・指標・市場テーマ等の具体材料）
【リスク・弱気材料】
- （箇条書きで最大3件）
【テクニカル所感】
- （株価水準・移動平均・出来高など、データから読み取れる範囲で）
【エントリー戦略】
- 想定エントリー価格帯と損切りライン（数字で）
- 想定保有期間と利確目安
【X直近センチメント】
- 強気/中立/弱気の割合と主要トピック
"""


def judge(code: str, aggregated_text: str, days_back: int = 3, model: str = DEFAULT_MODEL) -> dict:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")

    today = datetime.now()
    from_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT%H:%M:%SZ")

    prompt = JUDGE_PROMPT_TEMPLATE.format(days_back=days_back, aggregated=aggregated_text)

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
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    return {
        "code": code,
        "timestamp": today.isoformat(),
        "text": _extract_text(data),
        "citations": data.get("citations", []),
    }


def _extract_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return ""
