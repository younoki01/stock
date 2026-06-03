"""Slackチャンネル監視 → 銘柄コード検出 → データ収集 → 買い判定 → スレッド返信

使い方:
  python watcher.py                # 常駐ポーリング（デフォルト60秒間隔）
  python watcher.py --once         # 一度だけ実行
  python watcher.py --interval 30  # 30秒間隔で常駐
  python watcher.py --channel C... # チャンネルIDを上書き
  python watcher.py --test 7203    # 1銘柄を分析して標準出力に表示（Slackへは投稿しない）

環境変数:
  SLACK_BOT_TOKEN     - Bot Token (xoxb-...) 必須
  SLACK_WATCH_CHANNEL - 監視対象チャンネルID（デフォルト: C0B5EM0827Q）
  XAI_API_KEY         - Grok API キー 必須
"""

import argparse
import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv

from src import slack_client
from src.judge import judge
from src.stock_data import collect, format_for_prompt

load_dotenv()

DEFAULT_CHANNEL = "C0B49QLHHRU"
DEFAULT_INTERVAL_SEC = 60
STATE_PATH = Path(__file__).parent / ".watcher_state.json"

# 日本株コード:
#   - 旧形式: 4桁数字 (例 7203)
#   - 新形式: 5文字英数（先頭数字、TSE 2024年導入の英文字含有コード 例 130A0）
# 米国株: $TICKER または単独大文字 2-5 文字（ブラックリスト除外）
JP_CODE_RE = re.compile(r"(?<![0-9A-Za-z])([0-9][0-9A-Z]{3,4})(?![0-9A-Za-z])")
US_DOLLAR_RE = re.compile(r"\$([A-Z]{1,5})\b")
US_BARE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,5})(?![A-Za-z0-9])")

# 米株判定で誤検出されやすい英略語の除外リスト
US_BLACKLIST = {
    # 一般略語
    "OK", "NG", "FYI", "ETA", "TBD", "ASAP", "DM", "PR", "IR", "PM", "AM",
    "USA", "UK", "EU", "JP", "JST", "GMT", "UTC", "TV",
    # 技術
    "AI", "IT", "API", "URL", "PDF", "HTML", "CSS", "JSON", "XML", "SQL",
    "OS", "PC", "EV", "GPU", "CPU", "RAM", "SSD", "USB", "ID", "UI", "UX",
    # 役職
    "CEO", "CFO", "CTO", "COO", "CMO", "CIO",
    # 動詞・前置詞・形容詞
    "AND", "OR", "BUT", "FOR", "THE", "WITH", "FROM", "INTO", "ON", "OFF",
    "IN", "OUT", "UP", "DOWN", "YES", "NO", "NOT", "ALL", "ANY", "TOP",
    "NEW", "OLD", "GO", "STOP", "START", "END", "OPEN", "CLOSE",
    "BUY", "SELL", "HOLD", "LONG", "SHORT", "CALL", "PUT",
    "WILL", "CAN", "MAY", "BE", "IS", "ARE", "WAS", "WERE", "DO", "DID",
    # 単位・市場用語
    "USD", "JPY", "EUR", "BTC", "ETH",  # 通貨は対象外（株式コードとして扱わない）
    "NYSE", "NASDAQ", "TSE", "OTC", "ETF", "REIT", "IPO",
}


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_codes(text: str) -> list[str]:
    """テキストから銘柄コード候補を抽出。重複除去、出現順を保持。

    1. JP: 4桁数字 or 5文字英数（先頭数字）
    2. US: $TICKER（明示）
    3. US: 単独大文字 2-5 文字（ブラックリスト・JP既出を除外）
    """
    codes: list[str] = []
    seen: set[str] = set()

    for m in JP_CODE_RE.finditer(text):
        c = m.group(1)
        if c not in seen:
            codes.append(c)
            seen.add(c)

    for m in US_DOLLAR_RE.finditer(text):
        c = m.group(1)
        if c not in seen:
            codes.append(c)
            seen.add(c)

    for m in US_BARE_RE.finditer(text):
        c = m.group(1)
        if c in seen or c in US_BLACKLIST:
            continue
        codes.append(c)
        seen.add(c)

    return codes


def build_reply_blocks(code: str, data: dict, judge_result: dict) -> list:
    name = data.get("name", "")
    yahoo = data.get("yahoo", {})
    price = yahoo.get("price", "")
    change = yahoo.get("change", "")

    header_text = f"*{code}*"
    if name:
        header_text += f"  {name}"
    if price:
        header_text += f"  `{price}`"
    if change:
        header_text += f"  {change}"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header_text}},
        {"type": "section", "text": {"type": "mrkdwn", "text": judge_result["text"][:2900]}},
    ]

    # データソースのリンク
    links = []
    if yahoo.get("url"):
        links.append(f"<{yahoo['url']}|Yahoo>")
    if data.get("kabutan", {}).get("url"):
        links.append(f"<{data['kabutan']['url']}|株探>")
    if data.get("minkabu", {}).get("url"):
        links.append(f"<{data['minkabu']['url']}|みんかぶ>")
    if links:
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": " ｜ ".join(links)}]}
        )

    citations = judge_result.get("citations", [])[:5]
    if citations:
        link_lines = []
        for c in citations:
            url = c.get("url") or c.get("uri", "")
            if url:
                title = c.get("title", "X投稿")
                link_lines.append(f"• <{url}|{title}>")
        if link_lines:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*参照投稿*\n" + "\n".join(link_lines)},
                }
            )

    return blocks


def analyze_and_reply(channel: str, message: dict, dry_run: bool = False) -> list[str]:
    """1メッセージを処理。返信した銘柄コードリストを返す。"""
    text = message.get("text", "") or ""
    if message.get("bot_id"):
        return []  # 自分や他Botの投稿はスキップ
    if message.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
        return []

    codes = extract_codes(text)
    if not codes:
        return []

    ts = message["ts"]
    replied: list[str] = []
    for code in codes:
        print(f"  [{ts}] {code} 分析開始")
        data = collect(code)
        # いずれのソースからも銘柄名が取れなければ無効なコード扱い
        if not data.get("name"):
            print(f"    -> {code} は有効な銘柄として確認できず、スキップ")
            continue

        aggregated_text = format_for_prompt(data)
        judge_result = judge(code, aggregated_text)
        blocks = build_reply_blocks(code, data, judge_result)
        fallback = f"{code} {data.get('name', '')} 買い判定\n{judge_result['text'][:200]}"

        if dry_run:
            print("---DRY RUN---")
            print(aggregated_text)
            print("---JUDGE---")
            print(judge_result["text"])
        else:
            slack_client.post_thread_reply(channel, ts, text=fallback, blocks=blocks)
            print(f"    -> {code} スレッド返信完了")
        replied.append(code)

    return replied


def poll_once(channel: str, state: dict, dry_run: bool = False) -> None:
    last_ts = float(state.get("last_ts", 0))
    messages = slack_client.fetch_channel_history(channel, oldest=last_ts if last_ts else None)
    if not messages:
        return

    new_last_ts = last_ts
    for msg in messages:
        ts_float = float(msg["ts"])
        if ts_float <= last_ts:
            continue
        try:
            analyze_and_reply(channel, msg, dry_run=dry_run)
        except Exception as e:
            print(f"  [{msg.get('ts')}] エラー: {e}")
        if ts_float > new_last_ts:
            new_last_ts = ts_float

    if new_last_ts > last_ts:
        state["last_ts"] = new_last_ts
        save_state(state)


def main():
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="一度だけ実行して終了")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SEC, help="ポーリング間隔(秒)")
    parser.add_argument("--channel", type=str, default=None, help="監視チャンネルIDを上書き")
    parser.add_argument("--test", type=str, default=None, help="指定銘柄を分析して標準出力（Slack投稿なし）")
    parser.add_argument("--reset", action="store_true", help="既読状態をリセットして起動時に過去を遡らない")
    args = parser.parse_args()

    channel = args.channel or os.environ.get("SLACK_WATCH_CHANNEL") or DEFAULT_CHANNEL

    if args.test:
        code = args.test.upper()
        print(f"=== TEST: {code} ===")
        data = collect(code)
        aggregated = format_for_prompt(data)
        print(aggregated)
        print("\n=== JUDGE ===")
        result = judge(code, aggregated)
        print(result["text"])
        return

    state = load_state()
    if args.reset or "last_ts" not in state:
        # 初回起動: 現時点以降のメッセージのみ拾う
        state["last_ts"] = time.time()
        save_state(state)
        print(f"既読状態を初期化（last_ts={state['last_ts']}）")

    if args.once:
        print(f"[once] チャンネル {channel} を1回チェック")
        poll_once(channel, state)
        return

    print(f"[watch] チャンネル {channel} を {args.interval}秒間隔で監視開始（Ctrl+Cで停止）")
    while True:
        try:
            poll_once(channel, state)
        except Exception as e:
            print(f"poll エラー: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
