"""
個別銘柄を分析する CLI ツール

使い方:
  python analyze.py 7203          # コンソールに出力
  python analyze.py NVDA
  python analyze.py 7203 --slack  # Slack にも投稿
  python analyze.py 7203 --days 7 # 過去7日間を対象
"""

import argparse
import json
from dotenv import load_dotenv
from src.analyzer import analyze_stock
from src.scrapers.stock_detail import fetch_detail

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="個別銘柄の分析")
    parser.add_argument("code", help="銘柄コード（例: 7203, NVDA）")
    parser.add_argument("--days", type=int, default=3, help="遡る日数（デフォルト: 3）")
    parser.add_argument("--slack", action="store_true", help="Slack にも投稿")
    args = parser.parse_args()

    code = args.code.upper()

    print(f"\n{code} を分析中...\n")

    detail = fetch_detail(code)
    result = analyze_stock(code, days_back=args.days)

    _print_result(detail, result)

    if args.slack:
        from src.slack import post_stock_analysis
        post_stock_analysis(detail, result)
        print("\nSlack に投稿しました")


def _print_result(detail: dict, result: dict) -> None:
    name = detail.get("name", "")
    price = detail.get("price", "")
    change = detail.get("change", "")

    header = f"=== {result['code']}"
    if name:
        header += f" {name}"
    if price:
        header += f"  {price}"
    if change:
        header += f" ({change})"

    print(header)
    print("=" * len(header))
    print(result["text"])

    if result["citations"]:
        print("\n--- 参照投稿 ---")
        for c in result["citations"][:5]:
            url = c.get("url") or c.get("uri", "")
            if url:
                print(f"  {url}")


if __name__ == "__main__":
    main()
