import argparse
import os
from dotenv import load_dotenv
from src.fetcher import fetch_hot_stocks

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Xからホットな株情報を取得")
    parser.add_argument(
        "--days", type=int, default=1, help="何日前まで遡るか（デフォルト: 1）"
    )
    parser.add_argument(
        "--model", type=str, default="grok-3", help="使用するモデル（デフォルト: grok-3）"
    )
    args = parser.parse_args()

    print(f"X から過去 {args.days} 日間のホット株情報を取得中...\n")

    result = fetch_hot_stocks(days_back=args.days, model=args.model)

    print(f"取得日時: {result['timestamp']}")
    print(f"検索期間: {result['from_date']} 〜 {result['to_date']}")
    print("-" * 60)
    print(result["text"])

    if result["citations"]:
        print("\n--- 参照投稿 ---")
        for c in result["citations"][:10]:
            url = c.get("url") or c.get("uri", "")
            title = c.get("title", "")
            if url:
                print(f"  {title}  {url}" if title else f"  {url}")


if __name__ == "__main__":
    main()
