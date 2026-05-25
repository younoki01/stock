import os
import requests
from datetime import datetime


def _webhook_post(blocks: list) -> None:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("SLACK_WEBHOOK_URL が設定されていません")
    response = requests.post(webhook_url, json={"blocks": blocks}, timeout=10)
    response.raise_for_status()


def post_to_slack(grok_text: str, citations: list, rankings_text: str = "", watchlist_blocks: list = None, strategy_text: str = "", strategy_100k_text: str = "") -> None:
    date_str = datetime.now().strftime("%Y/%m/%d")
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📈 ホット株情報 {date_str}"},
        },
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "*🐦 X (Grok) 注目銘柄*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": grok_text}},
    ]

    if rankings_text:
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*📊 国内サイト 値上がりランキング*"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": rankings_text}},
        ]

    if strategy_text:
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*💴 100万円運用戦略*"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": strategy_text}},
        ]

    if strategy_100k_text:
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*🪙 10万円運用戦略*"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": strategy_100k_text}},
        ]

    if watchlist_blocks:
        blocks += [{"type": "divider"}] + watchlist_blocks

    if citations:
        links = "\n".join(
            f"• <{c.get('url') or c.get('uri', '')}|{c.get('title', 'X投稿')}>"
            for c in citations[:10]
            if c.get("url") or c.get("uri")
        )
        if links:
            blocks += [
                {"type": "divider"},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*参照投稿*\n{links}"}},
            ]

    _webhook_post(blocks)


def post_stock_analysis(detail: dict, result: dict) -> None:
    """個別銘柄分析を単体でSlackに投稿"""
    blocks = _build_analysis_blocks(detail, result)
    _webhook_post(blocks)


def build_watchlist_blocks(analyses: list[tuple[dict, dict]]) -> list:
    """ウォッチリスト分析ブロックを生成。analyses = [(detail, result), ...]"""
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*🔍 ウォッチリスト 個別分析*"}},
    ]
    for detail, result in analyses:
        blocks += _build_analysis_blocks(detail, result)
        blocks.append({"type": "divider"})
    return blocks[:-1]  # 末尾のdividerを除去


def _build_analysis_blocks(detail: dict, result: dict) -> list:
    code = result["code"]
    name = detail.get("name", "")
    price = detail.get("price", "")
    change = detail.get("change", "")

    header = f"*{code}*"
    if name:
        header += f"  {name}"
    if price:
        header += f"  `{price}`"
    if change:
        header += f"  {change}"

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "section", "text": {"type": "mrkdwn", "text": result["text"]}},
    ]
