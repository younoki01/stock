import os
import requests
from datetime import datetime


def _webhook_post(blocks: list) -> None:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("SLACK_WEBHOOK_URL が設定されていません")
    response = requests.post(webhook_url, json={"blocks": blocks}, timeout=10)
    response.raise_for_status()


def post_to_slack(grok_text: str, citations: list, rankings_text: str = "", watchlist_blocks: list = None, strategy_text: str = "", strategy_100k_text: str = "", bubble_text: str = "", accounts_text: str = "", accounts_citations: list = None, news_digest_text: str = "", radar_text: str = "", disclosure_text: str = "") -> None:
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

    if disclosure_text:
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*📋 本日の重要な適時開示（TDnet）*"}},
        ]
        for chunk in _chunk_mrkdwn(disclosure_text, 2900):
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})

    if news_digest_text:
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*📰 注目銘柄の材料ダイジェスト（株探）*"}},
        ]
        for chunk in _chunk_mrkdwn(news_digest_text, 2900):
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})

    if radar_text:
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*🔎 有望株レーダー（テーマ早期検知）*"}},
        ]
        for chunk in _chunk_mrkdwn(radar_text, 2900):
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})

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

    if bubble_text:
        blocks += [{"type": "divider"}]
        # Slack section は 3000 文字制限。Grok 出力は通常 2000 字程度だが念のため分割
        for chunk in _chunk_mrkdwn(bubble_text, 2900):
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})

    if accounts_text:
        blocks += [
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*👀 注視アカウントの株式関連投稿*"}},
        ]
        for chunk in _chunk_mrkdwn(accounts_text, 2900):
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
        if accounts_citations:
            links = " ｜ ".join(
                f"<{c.get('url') or c.get('uri', '')}|{c.get('title', 'X投稿')}>"
                for c in accounts_citations[:5]
                if c.get("url") or c.get("uri")
            )
            if links:
                blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": links}]})

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


def post_alert(header: str, body: str) -> None:
    """BOT用の軽量アラートを投稿する（日次レポートとは別の単発通知）。"""
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{header}*"}}]
    for chunk in _chunk_mrkdwn(body, 2900):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
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


def _chunk_mrkdwn(text: str, limit: int) -> list[str]:
    """Slack section の 3000 字制限対策。改行優先で分割し、それでも超える場合は強制分割"""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buf = ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > limit:
            if buf:
                chunks.append(buf)
                buf = ""
            # 1行が limit を超えるなら強制分割
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
        buf = f"{buf}\n{line}" if buf else line
    if buf:
        chunks.append(buf)
    return chunks


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
