"""日経平均のバブル度を①〜⑥のフレームで評価して Slack 用テキストを返す。

Grok x_search で最新指標 (PER, 騰落レシオ, 日経VI, 信用評価損益率 等) を取得し、
スコア化・コメント化する。
"""
import os
import re
import requests
from datetime import datetime, timedelta

from src import usage_log

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"

BUBBLE_PROMPT_TEMPLATE = """
本日（{today}）の日本株市場（日経平均ベース）のバブル度を評価してください。

【データ取得方針・厳守】
- 主要指標は必ず最新の具体的な数値で埋めること。「(不明)」「データ取得不可」「-X.X%」等の空欄プレースホルダは絶対禁止。
- 数値が直接の公式ソースから取得できない場合は、以下の手順を必ず踏むこと:
  1. X (Twitter) 上で当該指標を引用している直近1〜2日の投稿を検索（日経新聞公式 @nikkei、株探 @kabutan_news、証券ブロガー等）
  2. 見つからない場合、Web検索ツールで「日経平均PER」「騰落レシオ」「信用評価損益率」等を直接検索
  3. 週次指標（信用評価損益率・信用買い残など）は直近公表値を「(○月○日時点)」付きで記載
  4. どうしても取得不能な場合は「(直近1ヶ月の概算レンジ: XX〜XX)」と推定範囲を必ず書く。空欄や X プレースホルダのまま提出しないこと
- 必ず数値の出典を末尾に1行で明記すること（例: 出典: 日経新聞インデックス、株探警告銘柄ページ）

【Slack mrkdwn 形式の厳守】
- 太字は *単一アスタリスク* で囲む。**二重アスタリスク** は Slack では効かないので絶対使わない
- 見出しや強調はすべて *単一* で統一

【参考データ（本日朝の市場分析・既に取得済み）】
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
【参照すべき公開ソース（X検索 or Web検索のヒント）】
- 日経平均PER/PBR: 日経公式 indexes.nikkei.co.jp、Bloomberg、X上の @nikkei
- 騰落レシオ25日: 株探 kabutan.jp/warning、ヤフーファイナンス
- 日経VI: 大証/JPX公式、Yahoo Finance ^NKVI
- 信用評価損益率: 松井証券 finance.matsui.co.jp/stock/margin-investor （週次火曜更新）
- 200日線乖離率: 日経平均終値と200日移動平均から計算
- バフェット指標: 東証時価総額÷日本名目GDP（みんかぶ、個人投資家ブログ等）

---
【出力形式・厳守】

🌡️ *バブル恐怖指数: XX / 100点*
判定: ◯◯◯ （凡例: 〜30=冷静, 31-50=やや警戒, 51-70=警戒, 71-85=危険, 86-100=バブル末期）

*主要指標スナップショット* （必ず数値を入れる。空欄禁止）
• 日経平均PER: XX.X倍 (前週比 ±X.X) 　基準: 16倍以下=割安, 20倍超=過熱
• 騰落レシオ25日: XXX (前週比 ±X) 　基準: 80以下=底値, 120超=過熱, 140超=危険
• 日経VI: XX.X 　基準: 15以下=油断, 30超=恐慌
• 信用評価損益率: -X.X% (○月○日時点) 　基準: -15%以下=底値, 0%付近=天井
• 200日線乖離率: +X.X% (日経終値XX,XXX円 vs 200日線XX,XXX円) 　基準: +20%超=過熱
• バフェット指標(日本): XXX% 　基準: 100%超=割高, 150%超=バブル

*カテゴリ別評価* (A=極めて健全, B=健全, C=中立, D=警戒, E=危険)
① バリュエーション: X / 一言根拠（数値ベースで）
② センチメント: X / 一言根拠
③ 市場構造: X / 一言根拠
④ テクニカル: X / 一言根拠
⑤ マクロ: X / 一言根拠
⑥ 定性(空気感): X / 一言根拠

*総合コメント*
2〜3文で「今が買い場か、利確すべき局面か」を断定的に書く。曖昧な両論併記は避ける。

*出典*
（参照したソースを1行で。例: 日経公式インデックス、株探警告銘柄、@nikkei X投稿2件、Web検索）

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
        "tools": [
            {"type": "x_search", "from_date": from_date, "to_date": to_date},
            # web_search で日経公式・株探等の数値ページを直接読みに行かせる
            {"type": "web_search"},
        ],
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
    usage_log.record("bubble", model, data)

    text = _to_slack_mrkdwn(_extract_text(data))

    return {
        "timestamp": today.isoformat(),
        "text": text,
    }


def _to_slack_mrkdwn(text: str) -> str:
    """Markdown の **太字** / ***強強調*** を Slack の *太字* に正規化。

    Grok は癖で **bold** や ***bolditalic*** を返すことが多いので、
    連続するアスタリスクを単一に潰す。改行は跨がない（隣接見出しが連結するため）。
    """
    # **bold** / ***bold*** → *bold* （連続2個以上の囲みを単一に、改行跨ぎなし）
    text = re.sub(r"\*{2,}([^*\n]+?)\*{2,}", r"*\1*", text)
    # 残った 2個以上連続のアスタリスクを単一に
    text = re.sub(r"\*{2,}", "*", text)
    # 同一行内で隣接した空太字 *  * のみ除去（改行は跨がない）
    text = re.sub(r"\*[ \t]*\*", "", text)
    return text


def _extract_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return ""
