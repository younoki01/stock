"""指定した X アカウントの直近投稿から株式関連の内容だけを抽出して Slack 用テキストを返す。

対象アカウント:
  @pelositracker   - 米議員（ペロシ等）の株取引開示トラッカー。誰がどの銘柄を売買したか
  @realDonaldTrump - トランプ氏の発言（関税・金融政策・企業/業界への言及など、株式市場に影響）

Grok の x_search で対象ハンドルの投稿を検索し、株式に無関係な投稿は捨ててサマリ化する。
"""
import os
import re
import requests
from datetime import datetime, timedelta

from src import usage_log

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"

# 注視対象アカウント（ハンドル, 説明, 何を見るか）
WATCH_ACCOUNTS = [
    (
        "pelositracker",
        "米議員の株取引開示トラッカー",
        "どの議員がどの銘柄（ティッカー）を売買・オプション取引したか。金額・方向（買い/売り）も",
    ),
    (
        "realDonaldTrump",
        "トランプ氏の発言",
        "関税・金融政策・特定企業や業界への言及など、株式市場・個別銘柄に影響しうる発言",
    ),
    (
        "sou_btc",
        "暗号資産・相場系の個人投資家",
        "ビットコイン/暗号資産の相場観、注目トークン・銘柄、株式市場やマクロ環境への言及",
    ),
    (
        "fujimaki_takesi",
        "藤巻健史（経済評論家・元参議院議員）",
        "為替・円安・日銀金融政策・債券市場・ハイパーインフレ論、株式市場やマクロ環境への警鐘",
    ),
]

PROMPT_TEMPLATE = """
以下の X アカウントについて、直近 {days_back} 日間の投稿のうち
「株式・暗号資産・金融市場・特定銘柄（ティッカー）」に関連する内容だけを抽出して要約してください。

【対象アカウントと注目点】
{accounts_block}

【厳守事項】
- 相場・市場に無関係な投稿（私生活、政治の一般論、選挙運動など）は完全に無視すること
- 上記の対象アカウントごとに見出しを立て、各アカウントの該当投稿をまとめること
- 該当する投稿が無いアカウントは見出しの下に「該当なし」とだけ書くこと
- 各項目は「銘柄/ティッカー/対象：要点（投稿の趣旨）／（投稿日 M/D）」の形式
- 推測で銘柄を補わない。投稿に明記された情報のみ
- 太字は *単一アスタリスク* で囲む（**二重** は Slack で効かないので禁止）

【出力形式】
対象アカウントごとに、以下の形式で順に出力すること（アカウント数だけ見出しを作る）:

*@<ハンドル>（<説明>）*
• 銘柄/対象：要点 ／（M/D）
（該当が無ければ「該当なし」）

日本語、Slack mrkdwn 形式で回答してください。
"""


def fetch_account_posts(days_back: int = 1, model: str = DEFAULT_MODEL) -> dict:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")

    today = datetime.now()
    from_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT%H:%M:%SZ")

    accounts_block = "\n".join(
        f"- @{handle}（{desc}）: {focus}" for handle, desc, focus in WATCH_ACCOUNTS
    )
    prompt = PROMPT_TEMPLATE.format(days_back=days_back, accounts_block=accounts_block)

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

    usage_log.record("accounts", model, data)
    text = _to_slack_mrkdwn(_extract_text(data))
    citations = data.get("citations", [])

    return {
        "timestamp": today.isoformat(),
        "from_date": from_date,
        "to_date": to_date,
        "text": text,
        "citations": citations,
    }


def _to_slack_mrkdwn(text: str) -> str:
    """Markdown の **太字** を Slack の *太字* に正規化（bubble.py と同方針）。"""
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
