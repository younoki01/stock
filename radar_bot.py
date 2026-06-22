"""有望株探索BOT: PC稼働中に繰り返し銘柄を探す常駐ループ。

設計（コスト暴走を防ぐ）:
  - イベント駆動: 新規の重要開示(TDnet)を検知したらLLMで分析し、注目なら Slack 通知
  - 定期: 場中(JST 09-15)に最大1時間ごと軽量レーダーを回し、新候補が出たら通知
  - 予算ガード: 当日コスト(usage_log)が上限に達したらLLM停止（無料ポーリングは継続）
  - 場中は短間隔、場外は長間隔。同じ開示/候補は二度通知しない（state で重複排除）

使い方:
  python radar_bot.py                  # 常駐
  python radar_bot.py --once           # 1サイクルだけ実行
  python radar_bot.py --budget 0.5     # 日次LLM上限(USD)
  python radar_bot.py --radar-now      # 起動時に必ずレーダーを1回回す（テスト用）

環境変数: XAI_API_KEY, SLACK_WEBHOOK_URL
"""
import argparse
import json
import os
import re
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from src import db, market_data, slack, usage_log
from src.opportunity_radar import generate_radar
from src.scrapers import tdnet
from src.scrapers.aggregator import fetch_all_rankings, format_rankings

load_dotenv()

API_URL = "https://api.x.ai/v1/responses"
JST = timezone(timedelta(hours=9))
STATE_PATH = Path(__file__).parent / "bot_state.json"
JP_CODE_RE = re.compile(r"(?<![0-9A-Za-z])([0-9][0-9A-Z]{3,4})(?![0-9A-Za-z])")

DEFAULT_BUDGET = 0.5          # 日次LLM上限(USD)
ACTIVE_INTERVAL = 300         # 場中ポーリング間隔(秒)
IDLE_INTERVAL = 1800          # 場外ポーリング間隔(秒)
RADAR_INTERVAL = 3600         # 定期レーダーの最小間隔(秒)
MAX_DISCLOSURE_LLM = 4        # 1サイクルでLLM分析する新規開示の上限

DISCLOSURE_PROMPT = """\
次の適時開示が出ました。株価インパクトと「短期の買い候補として注目すべきか」を判定してください。

銘柄: {code} {name}
開示: {title}
テクニカル(直近): {tech}

【判定基準】
- 上方修正/自社株買い/受注/提携など実益のある材料か、定型・軽微か
- テクニカルで既に過熱(RSI高・高値圏・急騰済み)なら出遅れ妙味は薄い

出力(Slack mrkdwn・3行以内):
判定: 注目 / 中立 / スルー
理由: <材料の重要度と出遅れ/過熱を一言>
"""


# ---- state ----

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"seen_disclosures": [], "alerted": {}, "last_radar_ts": 0, "budget_notified": ""}


def save_state(s: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---- time / budget ----

def now_jst() -> datetime:
    return datetime.now(JST)


def is_active(now: datetime) -> bool:
    """場中＋引け後の材料が出る時間帯（平日 09:00-16:30 JST）。"""
    return now.weekday() < 5 and dtime(9, 0) <= now.time() < dtime(16, 30)


def is_radar_window(now: datetime) -> bool:
    return now.weekday() < 5 and dtime(9, 0) <= now.time() < dtime(15, 0)


def budget_ok(cap: float) -> bool:
    return usage_log.today_cost() < cap


# ---- LLM ----

def _llm(prompt: str, label: str, model: str = "grok-3-mini") -> str:
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY が設定されていません")
    r = requests.post(
        API_URL,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={"model": model, "input": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    usage_log.record(label, model, data)
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    return c.get("text", "")
    return ""


# ---- event: 重要開示 ----

def _disc_key(d: dict) -> str:
    return f"{d.get('code','')}|{d.get('title','')[:30]}"


def analyze_disclosure(d: dict) -> None:
    code, name = d.get("code", ""), d.get("name", "")
    tech = market_data.technicals(code) if code else {}
    tech_s = (
        f"株価{tech.get('price','-')} RSI{tech.get('rsi14','-')} 高値から{tech.get('from_high_pct','-')}% "
        f"20日{tech.get('ret_20d_pct','-')}%" if tech else "（時系列取得不可）"
    )
    text = _llm(
        DISCLOSURE_PROMPT.format(code=code, name=name, title=d.get("title", ""), tech=tech_s),
        label="bot_disclosure",
    )
    first = text.strip().splitlines()[0] if text.strip() else ""
    if "注目" in first:
        slack.post_alert(f"🚨 開示速報 {code} {name}［{d.get('category','')}］", text)
        print(f"  [通知] {code} {name}: 注目")
    else:
        print(f"  [スルー] {code} {name}: {first[:30]}")


# ---- periodic: レーダー ----

def run_radar(state: dict, material: list) -> None:
    try:
        rankings_text = format_rankings(fetch_all_rankings(top_n=10))
    except Exception:
        rankings_text = ""
    res = generate_radar("", rankings_text, {}, disclosures=material)
    db.save_prices({c["code"]: c.get("px") for c in res.get("candidates", [])})

    today = now_jst().strftime("%Y-%m-%d")
    alerted = set(state["alerted"].get(today, []))
    codes_in_text = [m.group(1) for m in JP_CODE_RE.finditer(res["text"])]
    cand_codes = {c["code"] for c in res.get("candidates", [])}
    new_codes = [c for c in codes_in_text if c in cand_codes and c not in alerted]

    if new_codes:
        slack.post_alert(f"🔁 有望株レーダー更新（新候補: {', '.join(dict.fromkeys(new_codes))}）", res["text"])
        alerted.update(new_codes)
        state["alerted"][today] = sorted(alerted)
        print(f"  [レーダー通知] 新候補 {new_codes}")
    else:
        print("  [レーダー] 新候補なし")


# ---- cycle ----

def cycle(state: dict, cap: float, force_radar: bool = False) -> None:
    now = now_jst()
    print(f"[{now.strftime('%H:%M:%S')}] サイクル開始  当日コスト ${usage_log.today_cost():.3f}/{cap}")

    # 1. 無料: 重要開示の新着検知
    seen = set(state["seen_disclosures"])
    material = tdnet.material(tdnet.fetch(limit=80))
    db.save_disclosures(material)
    new_disc = [d for d in material if _disc_key(d) not in seen]
    print(f"  重要開示 {len(material)}件 / 新規 {len(new_disc)}件")

    # 2. イベント駆動: 新規開示をLLM分析（予算内・上限件数）
    for d in new_disc[:MAX_DISCLOSURE_LLM]:
        seen.add(_disc_key(d))
        if budget_ok(cap):
            try:
                analyze_disclosure(d)
            except Exception as e:
                print(f"  [警告] 開示分析失敗: {e}")
        else:
            _notify_budget(state, cap)
    for d in new_disc:  # 分析しなかった分も既読化（再通知防止）
        seen.add(_disc_key(d))
    state["seen_disclosures"] = list(seen)[-800:]

    # 3. 定期レーダー（場中・最小間隔・予算内）
    due = force_radar or (now.timestamp() - state.get("last_radar_ts", 0) >= RADAR_INTERVAL)
    if (force_radar or is_radar_window(now)) and due:
        if budget_ok(cap):
            try:
                run_radar(state, material)
                state["last_radar_ts"] = now.timestamp()
            except Exception as e:
                print(f"  [警告] レーダー失敗: {e}")
        else:
            _notify_budget(state, cap)

    save_state(state)


def _notify_budget(state: dict, cap: float) -> None:
    today = now_jst().strftime("%Y-%m-%d")
    if state.get("budget_notified") != today:
        print(f"  [予算到達] 当日 ${usage_log.today_cost():.3f} ≥ ${cap}。LLM停止（無料ポーリングは継続）")
        state["budget_notified"] = today


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="1サイクルだけ実行")
    p.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help="日次LLM上限(USD)")
    p.add_argument("--radar-now", action="store_true", help="起動時にレーダーを必ず1回回す")
    args = p.parse_args()

    state = load_state()
    print(f"[BOT起動] 日次上限 ${args.budget} / 場中{ACTIVE_INTERVAL}s・場外{IDLE_INTERVAL}s間隔")

    if args.once:
        cycle(state, args.budget, force_radar=args.radar_now)
        return

    first = True
    while True:
        try:
            cycle(state, args.budget, force_radar=(first and args.radar_now))
        except Exception as e:
            print(f"サイクルエラー: {e}")
        first = False
        time.sleep(ACTIVE_INTERVAL if is_active(now_jst()) else IDLE_INTERVAL)


if __name__ == "__main__":
    main()
