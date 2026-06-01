"""日経平均のバブル度を①〜⑥のフレームで評価して Slack 用テキストを返す。

Grok x_search で最新指標 (PER, 騰落レシオ, 日経VI, 信用評価損益率 等) を取得し、
スコア化・コメント化する。
"""
import os
import requests
from datetime import datetime, timedelta

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"

BUBBLE_PROMPT_TEMPLATE = """
本日（{today}）の日本株市場（日経平均ベース）のバブル度を評価してください。
最新の数値は X (Twitter) 投稿および Web 検索で取得できる範囲で参照し、
取得できない指標は「データ取得不可」と明記してください（推測値で埋めないこと）。

【参考データ（本日朝の市場分析）】
X注目銘柄サマリ:
{hot_stocks_text}

国内値上がりランキング:
{rankings_text}

---
【評価フレームワーク】
① バリュエーション系: 日経平均PER, シラーPER(日本版), PBR, バフェット指標(時価総額÷GDP)
② センチメント系: 日経VI, 信用評価損益率, 信用買い残, Put/Call Ratio
③ 市場構造系: IPO件数・初値騰落率, レバETF(1357/1579)出来高, 新規証券口座開設
④ テクニカル系: 日経200日移動平均乖離率, 騰落レシオ(25日), 新高値-新安値銘柄数
⑤ マクロ系: イールドカーブ, クレジットスプレッド, 実質金利, M2伸び率
⑥ 定性系: メディア論調, SNS熱狂度, 「今回は違う」言説, 素人参入兆候

---
【出力形式・厳守】

🌡️ *バブル恐怖指数: XX / 100点*
判定: ◯◯◯ （凡例: 〜30=冷静, 31-50=やや警戒, 51-70=警戒, 71-85=危険, 86-100=バブル末期）

*主要指標スナップショット*
• 日経平均PER: XX.X倍 （基準: 16倍以下=割安, 20倍超=過熱）
• 騰落レシオ25日: XXX （基準: 80以下=底値, 120超=過熱, 140超=危険）
• 日経VI: XX.X （基準: 15以下=油断, 30超=恐慌）
• 信用評価損益率: -X.X% （基準: -15%以下=底値, 0%付近=天井）
• 200日線乖離率: +X.X% （基準: +20%超=過熱）
• バフェット指標(日本): XXX% （基準: 100%超=割高, 150%超=バブル）
※取得不能な指標は「(不明)」と記載してこの形式を必ず維持

*カテゴリ別評価* (A=極めて健全, B=健全, C=中立, D=警戒, E=危険)
① バリュエーション: X / 一言根拠
② センチメント: X / 一言根拠
③ 市場構造: X / 一言根拠
④ テクニカル: X / 一言根拠
⑤ マクロ: X / 一言根拠
⑥ 定性(空気感): X / 一言根拠

*総合コメント*
2〜3文で「今が買い場か、利確すべき局面か」を断定的に書く。曖昧な両論併記は避ける。

日本語、Slack mrkdwn 形式で回答してください（見出しは *〜* で太字）。
"""


def evaluate_bubble(hot_stocks_text: str, rankings_text: str, model: str = DEFAULT_MODEL) -> dict:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")

    today = datetime.now()
    from_date = (today - timedelta(days=2)).strftime("%Y-%m-%dT00:00:00Z")
    to_date = today.strftime("%Y-%m-%dT%H:%M:%SZ")

    prompt = BUBBLE_PROMPT_TEMPLATE.format(
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
        timeout=120,
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
