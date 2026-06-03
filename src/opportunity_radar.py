"""有望株レーダー: 上流シグナル＋材料から「テーマ→出遅れ受益銘柄」を発掘する。

フロー:
  1. 上流シグナル収集: TrendForce(メモリ/半導体) ＋ 既収集の株探材料/X/ランキング [無料]
  2. LLM-A: 盛り上がりつつあるテーマ抽出（因果仮説＋signal強度＋候補コード）
  3. 裏付け: 候補の日本株を株探個別ページで PER/PBR/株価/年初来高安 付与
  4. LLM-B: 出遅れ度・指標・懐疑を加味してスコアリング＆ランク
  5. L1: テーマを state 保存 → 新規/強化を検出して見出しに表示
  6. L2: 拾った候補を価格付きでログ → 成熟したピックの先行リターンを次回へ還元

Live Search は使わない（純トークン代のみ）。
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests

from src import market_data, usage_log
from src.scrapers import trendforce
from src.scrapers.kabutan_detail import fetch as fetch_kabutan_detail

API_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-3"
JP_CODE_RE = re.compile(r"(?<![0-9A-Za-z])([0-9][0-9A-Z]{3,4})(?![0-9A-Za-z])")

_ROOT = Path(__file__).parent.parent
STATE_PATH = _ROOT / "radar_state.json"
PICKS_LOG_PATH = _ROOT / "picks_log.json"

MATURE_DAYS = 7        # 何日後のリターンで評価するか
MAX_EVAL_PER_RUN = 5   # 1回の実行で再取得する過去ピック数の上限
MAX_ENRICH = 10        # 裏付けする日本株候補の上限

EXTRACT_PROMPT = """\
あなたは「上流シグナルから出遅れ受益銘柄を発掘するアナリスト」です。
以下の上流シグナルと市場材料から、今“盛り上がりつつある/強まっている”投資テーマを最大5つ抽出してください。

【上流シグナル: TrendForce（メモリDRAM/NAND・HBM・半導体の業界動向）】
{trendforce_block}

【本日の重要な適時開示（TDnet・公式の早期材料）】
{disclosure_block}

【X注目銘柄】
{hot_stocks_text}

【国内の材料ニュース（株探）】
{news_block}

【本日の値上がりランキング】
{rankings_text}

【指示】
- 各テーマに因果の連鎖を一言（このシグナル→どの企業の利益が増えるか）
- signal は 1〜5（5=シグナルが強く確度が高い／単発の煽りは低く）
- 受益銘柄は1次（直接）だけでなく2次（製造装置・材料・商社・電力等）も含める
- 日本株は必ず証券コード付き（例: キオクシア(285A)）。米国株はティッカー

【出力形式（厳守・この形式以外書かない）】
THEMES:
- <テーマ名> | signal=<1-5> | <因果一言> | 受益: 社名(コード), 社名(コード)
CANDIDATES_JP: <コード>, <コード>, ...
"""

SCORE_PROMPT = """\
以下の抽出テーマと、各候補銘柄の実データを踏まえ、
「シグナルは強いのに株価がまだ反応しきっていない＝出遅れ」の観点で有望株をランク付けしてください。

【抽出テーマ】
{themes_block}

【候補銘柄の実データ（株探）】
{enriched_block}

【過去ピックの実績（自己フィードバック）】
{feedback_block}

【評価軸】
- 出遅れ度（テクニカル実データで判定。重要）:
  ・RSI70以上 / 高値からの距離が0%付近 / 20日騰落が大きくプラス → 「過熱・天井圏」であり出遅れではない（強く減点）
  ・RSI40〜55 / 高値から-15%以上下 / MA25乖離が小さい〜マイナス → 「出遅れ・押し目」（加点）
  ・出来高倍率が高い → 既に急騰・動意づき済み（出遅れとは逆。注意）
- テーマ強度: signal が高いテーマの銘柄を優先
- 指標: 極端な割高(高PER/PBR)は減点
- 懐疑: pump臭・既に織り込み済み・仕手は明記して減点

【出力の厳守事項】
- 各銘柄の3つの箇条書きは、必ずその銘柄固有の“具体的な中身”で埋めること。
- 下記テンプレートの <...> は説明であり、そのまま出力するのは禁止。必ず実際の内容に置換する。
- 強気仮説には「どの上流シグナル → なぜこの企業の利益が増えるか」の因果を必ず書く。
- リスク・エントリー/損切りは、実データの株価・指標を根拠に具体的に書く。

【出力テンプレート（Slack mrkdwn・上位5銘柄。<...>は実際の内容に置換すること）】
<順位>. *<社名>(<コード>)* ｜ テーマ:<テーマ名> ｜ 出遅れ度:<★を1〜3個> ｜ 確信度:<★を1〜3個>
   • 強気仮説: <シグナル→利益増の因果を1〜2文で具体的に>
   • リスク/懐疑: <この銘柄固有の pump/織り込み済み/割高 などの懸念>
   • 想定: <エントリー価格帯と損切りラインを実際の数値で>

最後に *⚠️ 注意* として「これは投資助言ではなく候補スクリーニングである」旨を1行。
太字は *単一アスタリスク*。日本語、Slack mrkdwn 形式で。
"""


def generate_radar(hot_stocks_text: str, rankings_text: str, news_by_code: dict, disclosures: list = None, model: str = DEFAULT_MODEL) -> dict:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")

    # 1. 上流シグナル
    tf_items = trendforce.fetch(limit=15)
    tf_block = "\n".join(f"- [{it['tag']}] {it['title']}" for it in tf_items) or "（取得なし）"
    news_block = _format_news_block(news_by_code)
    disclosure_block = "\n".join(
        f"- {d.get('code','')} {d.get('name','')}［{d.get('category','')}］{d.get('title','')[:50]}"
        for d in (disclosures or [])[:25]
    ) or "（なし）"

    # 2. LLM-A: テーマ抽出
    extract_text = _call_llm(api_key, model, EXTRACT_PROMPT.format(
        trendforce_block=tf_block,
        disclosure_block=disclosure_block,
        hot_stocks_text=hot_stocks_text or "（なし）",
        news_block=news_block or "（なし）",
        rankings_text=rankings_text or "（なし）",
    ), label="radar_extract")
    themes, cand_codes = _parse_extract(extract_text)

    # 3. 候補の裏付け（株探）
    enriched = _enrich(cand_codes[:MAX_ENRICH])
    enriched_block = _format_enriched(enriched) or "（裏付けデータなし）"
    themes_block = "\n".join(f"- {t['name']} | signal={t['signal']}" for t in themes) or extract_text

    # 5(先): L2 フィードバック要約（成熟ピックを評価）
    feedback_block = _summarize_feedback()

    # 4. LLM-B: スコアリング
    radar_text = _to_slack_mrkdwn(_call_llm(api_key, model, SCORE_PROMPT.format(
        themes_block=themes_block,
        enriched_block=enriched_block,
        feedback_block=feedback_block,
    ), label="radar_score"))

    # 5. L1: テーマの新規/強化を検出して見出しに付与
    headline = _theme_delta_headline(themes)
    if headline:
        radar_text = headline + "\n\n" + radar_text

    # 6. L2: 本日サーフェスした銘柄をログ
    _log_picks(radar_text, enriched)

    return {
        "timestamp": datetime.now().isoformat(),
        "text": radar_text,
        "themes": themes,
        "candidates": enriched,
    }


# ---- 収集・整形 ----

def _format_news_block(news_by_code: dict) -> str:
    if not news_by_code:
        return ""
    lines = []
    for code, items in news_by_code.items():
        for it in items[:4]:
            lines.append(f"- {code} {it['datetime']} [{it['category']}] {it['title']}")
    return "\n".join(lines)


def _parse_extract(text: str):
    """LLM-A 出力から themes と日本株候補コードを抽出。"""
    themes = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("-") or "signal=" not in line:
            continue
        name = line.lstrip("- ").split("|")[0].strip()
        m = re.search(r"signal\s*=\s*([1-5])", line)
        signal = int(m.group(1)) if m else 3
        themes.append({"name": name, "signal": signal})

    codes = []
    seen = set()
    cand_line = ""
    for line in text.splitlines():
        if "CANDIDATES_JP" in line:
            cand_line = line.split(":", 1)[-1]
            break
    source = cand_line if cand_line else text
    for m in JP_CODE_RE.finditer(source):
        c = m.group(1)
        if c not in seen:
            codes.append(c)
            seen.add(c)
    return themes, codes


def _enrich(codes: list[str]) -> list[dict]:
    out = []
    for code in codes:
        try:
            d = fetch_kabutan_detail(code)
        except Exception:
            continue
        if not d.get("supported") or not d.get("name"):
            continue
        name = d.get("name", "")
        if name.startswith(code):  # 銘柄名先頭にコードが重複する場合は除去
            name = name[len(code):].strip()
        tech = market_data.technicals(code)  # OHLCVベースのテクニカル（空dictの場合あり）
        out.append({
            "code": code,
            "name": name,
            "per": d.get("per", ""),
            "pbr": d.get("pbr", ""),
            "price": (tech.get("price") if tech else None) or d.get("price", ""),
            "px": tech.get("price") if tech else None,  # 数値（フィードバックのリターン計算用）
            "tech": tech,
        })
    return out


def _format_enriched(enriched: list[dict]) -> str:
    lines = []
    for e in enriched:
        t = e.get("tech") or {}
        line = f"- {e['code']} {e['name']}: PER{e['per'] or '-'} PBR{e['pbr'] or '-'}"
        if t:
            line += (
                f" ｜ 株価{t['price']} RSI{t.get('rsi14', '-')} "
                f"MA25乖離{t.get('ma25_dev_pct', '-')}% 高値から{t.get('from_high_pct', '-')}% "
                f"20日{t.get('ret_20d_pct', '-')}% 出来高{t.get('vol_spike', '-')}倍"
            )
        else:
            line += f" ｜ 株価{e['price'] or '-'}（時系列取得不可）"
        lines.append(line)
    return "\n".join(lines)


# ---- L1: テーマ状態追跡 ----

def _theme_delta_headline(themes: list[dict]) -> str:
    prev = {}
    if STATE_PATH.exists():
        try:
            prev = {t["name"]: t.get("signal", 0) for t in json.loads(STATE_PATH.read_text(encoding="utf-8")).get("themes", [])}
        except Exception:
            prev = {}

    new_t = [t["name"] for t in themes if t["name"] not in prev]
    strengthening = [t["name"] for t in themes if t["name"] in prev and t["signal"] > prev[t["name"]]]

    try:
        STATE_PATH.write_text(json.dumps(
            {"date": datetime.now().strftime("%Y-%m-%d"), "themes": themes},
            ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    parts = []
    if new_t:
        parts.append("🆕 新規テーマ: " + "、".join(new_t[:3]))
    if strengthening:
        parts.append("📈 強化中: " + "、".join(strengthening[:3]))
    return "  ｜  ".join(parts)


# ---- L2: ピックログ＆フィードバック ----

def _parse_price(s: str):
    if not s:
        return None
    m = re.search(r"[0-9][0-9,]*\.?[0-9]*", s.replace(",", ""))
    try:
        return float(m.group(0)) if m else None
    except Exception:
        return None


def _load_picks() -> list:
    if PICKS_LOG_PATH.exists():
        try:
            return json.loads(PICKS_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _log_picks(radar_text: str, enriched: list[dict]) -> None:
    price_map = {e["code"]: e["price"] for e in enriched}
    px_map = {e["code"]: e.get("px") for e in enriched}
    name_map = {e["code"]: e["name"] for e in enriched}
    surfaced = []
    seen = set()
    for m in JP_CODE_RE.finditer(radar_text):
        c = m.group(1)
        if c in price_map and c not in seen:
            surfaced.append(c)
            seen.add(c)

    if not surfaced:
        return
    picks = _load_picks()
    today = datetime.now().strftime("%Y-%m-%d")
    for c in surfaced:
        picks.append({
            "date": today,
            "code": c,
            "name": name_map.get(c, ""),
            "price": price_map.get(c, ""),
            "px": px_map.get(c),
            "ret_pct": None,
        })
    try:
        PICKS_LOG_PATH.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _summarize_feedback() -> str:
    picks = _load_picks()
    if not picks:
        return "（履歴なし。今回から記録開始）"

    today = datetime.now()
    evaluated_now = 0
    changed = False
    for p in picks:
        if p.get("ret_pct") is not None:
            continue
        try:
            age = (today - datetime.strptime(p["date"], "%Y-%m-%d")).days
        except Exception:
            continue
        if age < MATURE_DAYS or evaluated_now >= MAX_EVAL_PER_RUN:
            continue
        entry = p.get("px") or _parse_price(p.get("price", ""))
        if not entry:
            p["ret_pct"] = 0.0  # 価格不明は中立で確定
            changed = True
            continue
        cur = market_data.current_price(p["code"])  # yfinanceの直近終値
        if cur:
            p["ret_pct"] = round((cur - entry) / entry * 100, 1)
            changed = True
            evaluated_now += 1

    if changed:
        try:
            PICKS_LOG_PATH.write_text(json.dumps(picks, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    done = [p for p in picks if isinstance(p.get("ret_pct"), (int, float))]
    done = [p for p in done if p.get("price")]  # 価格ありのみ
    rated = [p for p in done if _parse_price(p.get("price", ""))]
    if not rated:
        return f"（記録 {len(picks)}件。{MATURE_DAYS}日成熟待ち。評価可能データはこれから蓄積）"

    n = len(rated)
    avg = round(sum(p["ret_pct"] for p in rated) / n, 1)
    win = round(sum(1 for p in rated if p["ret_pct"] > 0) / n * 100)
    best = max(rated, key=lambda p: p["ret_pct"])
    worst = min(rated, key=lambda p: p["ret_pct"])
    return (
        f"過去ピックの{MATURE_DAYS}日リターン: 平均{avg:+}% / 勝率{win}% (n={n})。"
        f"最良 {best['name']}({best['code']}) {best['ret_pct']:+}% / "
        f"最差 {worst['name']}({worst['code']}) {worst['ret_pct']:+}%。"
        "この傾向を踏まえ、効いた型を優先し外した型は減点すること。"
    )


# ---- LLM 共通 ----

def _call_llm(api_key: str, model: str, prompt: str, label: str = "radar") -> str:
    payload = {"model": model, "input": [{"role": "user", "content": prompt}]}  # tools 無し
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    usage_log.record(label, model, data)
    return _extract_text(data)


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
