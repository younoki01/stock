"""
毎朝 08:30 に X からホット株情報を取得して Slack に投稿する。

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

load_dotenv()

POST_TIME = "08:30"


def job():
    print(f"[実行] X からホット株情報を取得中...")
    try:
        result = fetch_hot_stocks(days_back=1)
        post_to_slack(result["text"], result["citations"])
        print("[完了] Slack に投稿しました")
    except Exception as e:
        print(f"[エラー] {e}")


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
