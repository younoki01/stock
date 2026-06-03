"""
毎朝 08:00 に X + 国内株サイトからホット株情報を取得して Slack に投稿する。

使い方:
  python scheduler.py          # スケジューラーを起動（常駐）
  python scheduler.py --now    # 即座に1回実行してテスト
"""

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import schedule
from dotenv import load_dotenv

from src import db
from src.accounts import fetch_account_posts
from src.bubble import evaluate_bubble
from src.fetcher import fetch_hot_stocks
from src.analyzer import analyze_stock
from src.news_digest import CODE_RE, generate_digest
from src.opportunity_radar import generate_radar
from src.scrapers import tdnet
from src.scrapers.aggregator import fetch_all_rankings, format_rankings
from src.scrapers.stock_detail import fetch_detail
from src.slack import post_to_slack, build_watchlist_blocks
from src.strategy import generate_strategy

load_dotenv()

POST_TIME = "08:00"
WATCHLIST_PATH = Path(__file__).parent / "watchlist.json"

JST = timezone(timedelta(hours=9))
BUBBLE_WEEKDAY = 0  # バブル評価を実行する曜日（0=月曜, JST基準）


def load_watchlist() -> list[str]:
    if not WATCHLIST_PATH.exists():
        return []
    return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))


def _is_bubble_day() -> bool:
    """バブル評価を実行する日か（JST基準の曜日で判定）。実行環境のTZに依存しない。"""
    return datetime.now(JST).weekday() == BUBBLE_WEEKDAY


def _digest_codes(watchlist: list[str], rankings: dict, max_codes: int = 8) -> list[str]:
    """材料ダイジェスト対象の日本株コードを選定（ウォッチリスト優先→ランキング上位）。"""
    codes: list[str] = []
    seen: set[str] = set()

    def add(code: str) -> None:
        if code and CODE_RE.match(code) and code not in seen:
            codes.append(code)
            seen.add(code)

    for c in watchlist:
        add(c)
    for stocks in rankings.values():
        for s in stocks:
            add(s.get("code", ""))
            if len(codes) >= max_codes:
                break
        if len(codes) >= max_codes:
            break
    return codes[:max_codes]


def job(force_bubble: bool = False):
    print("[実行] データ取得中...")

    # X (Grok) から注目銘柄
    grok_result = fetch_hot_stocks(days_back=1)
    print("[完了] Grok x_search 取得")

    # 国内サイトから値上がりランキング
    rankings = fetch_all_rankings(top_n=10)
    rankings_text = format_rankings(rankings)
    print("[完了] 国内サイトスクレイピング完了")

    # 適時開示（TDnet）から重要開示を抽出
    disclosures = tdnet.fetch(limit=80)
    material_disc = tdnet.material(disclosures)
    disclosure_text = tdnet.format_for_slack(material_disc, limit=12)
    db.save_disclosures(material_disc)
    print(f"[完了] 適時開示（重要{len(material_disc)}件）")

    # 注視アカウント（@pelositracker, @realDonaldTrump）の株式関連投稿
    accounts_result = fetch_account_posts(days_back=1)
    print("[完了] 注視アカウント投稿取得")

    # 注目銘柄の材料ダイジェスト（株探ニュースを順次収集 → LLM要約。Live Search不要）
    digest_codes = _digest_codes(load_watchlist(), rankings)
    digest_result = generate_digest(digest_codes)
    print(f"[完了] 材料ダイジェスト（{len(digest_result['news_by_code'])}銘柄）")

    # 有望株レーダー（上流シグナル＋材料→テーマ早期検知）。失敗してもレポートは継続
    radar_text = ""
    try:
        radar_result = generate_radar(
            grok_result["text"], rankings_text, digest_result["news_by_code"], disclosures=material_disc
        )
        radar_text = radar_result["text"]
        db.save_prices({c["code"]: c.get("px") for c in radar_result.get("candidates", [])})
        print(f"[完了] 有望株レーダー（テーマ{len(radar_result['themes'])}件）")
    except Exception as e:
        print(f"[警告] 有望株レーダー失敗（スキップ）: {e}")

    # ウォッチリスト個別分析
    watchlist = load_watchlist()
    watchlist_blocks = []
    if watchlist:
        analyses = []
        for code in watchlist:
            print(f"[分析中] {code}")
            detail = fetch_detail(code)
            result = analyze_stock(code, days_back=1)
            analyses.append((detail, result))
        watchlist_blocks = build_watchlist_blocks(analyses)
        print("[完了] ウォッチリスト分析完了")

    # 100万円運用戦略
    strategy_1m = generate_strategy(grok_result["text"], rankings_text, budget=1_000_000)
    print("[完了] 100万円運用戦略生成完了")

    # バブル恐怖指数評価（週1: 月曜JSTのみ。--now では強制実行）
    bubble_text = ""
    if force_bubble or _is_bubble_day():
        bubble_result = evaluate_bubble(grok_result["text"], rankings_text)
        bubble_text = bubble_result["text"]
        print("[完了] バブル恐怖指数評価完了")
    else:
        print("[スキップ] バブル恐怖指数は週1（月曜JST）のみ実行")

    post_to_slack(
        grok_result["text"],
        grok_result["citations"],
        rankings_text,
        watchlist_blocks,
        strategy_1m["text"],
        "",  # 10万円運用戦略は廃止
        bubble_text,
        accounts_text=accounts_result["text"],
        accounts_citations=accounts_result["citations"],
        news_digest_text=digest_result["text"],
        radar_text=radar_text,
        disclosure_text=disclosure_text,
    )
    print("[完了] Slack に投稿しました")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="今すぐ1回実行")
    args = parser.parse_args()

    if args.now:
        job(force_bubble=True)
        return

    schedule.every().day.at(POST_TIME).do(job)
    print(f"スケジューラー起動: 毎日 {POST_TIME} に Slack へ投稿します")
    print("停止するには Ctrl+C を押してください\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
