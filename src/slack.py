import os
import requests
from datetime import datetime


def post_to_slack(grok_text: str, citations: list, rankings_text: str = "") -> None:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("SLACK_WEBHOOK_URL が設定されていません")

    date_str = datetime.now().strftime("%Y/%m/%d")
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📈 ホット株情報 {date_str}"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*🐦 X (Grok) 注目銘柄*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": grok_text},
        },
    ]

    if rankings_text:
        blocks += [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*📊 国内サイト 値上がりランキング*"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": rankings_text},
            },
        ]

    if citations:
        links = "\n".join(
            f"• <{c.get('url') or c.get('uri', '')}|{c.get('title', 'X投稿')}>"
            for c in citations[:10]
            if c.get("url") or c.get("uri")
        )
        if links:
            blocks += [
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*参照投稿*\n{links}"},
                },
            ]

    response = requests.post(
        webhook_url,
        json={"blocks": blocks},
        timeout=10,
    )
    response.raise_for_status()
