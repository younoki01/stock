"""
毎朝 08:30 に X + 国内株サイトからホット株情報を取得して Slack に投稿する。

使い方:
  python scheduler.py          # スケジューラーを起動（常駐）
  python scheduler.py --now    # 即座に1回実行してテスト
"""

import argparse
import time
import schedule
from dotenv import load_dotenv
from src.fetcher import fetch_hot_stocks
from src.slack import post_to_slack
from src.scrapers.aggregator import fetch_all_rankings, format_rankings

load_dotenv()

POST_TIME = "08:30"


def job():
    print("[実行] データ取得中...")

    # X (Grok) から注目銘柄
    grok_result = fetch_hot_stocks(days_back=1)
    print("[完了] Grok x_search 取得")

    # 国内サイトから値上がりランキング
    rankings = fetch_all_rankings(top_n=10)
    rankings_text = format_rankings(rankings)
    print("[完了] 国内サイトスクレイピング完了")

    post_to_slack(grok_result["text"], grok_result["citations"], rankings_text)
    print("[完了] Slack に投稿しました")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="今すぐ1回実行")
    args = parser.parse_args()

    if args.now:
        job()
        return

    schedule.every().day.at(POST_TIME).do(job)
    print(f"スケジューラー起動: 毎日 {POST_TIME} に Slack へ投稿します")
    print("停止するには Ctrl+C を押してください\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
