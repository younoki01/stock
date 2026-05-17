import os
import requests
from datetime import datetime


def post_to_slack(text: str, citations: list) -> None:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("SLACK_WEBHOOK_URL が設定されていません")

    date_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    body = f"*📈 ホット株情報 ({date_str})*\n\n{text}"

    if citations:
        links = "\n".join(
            f"• <{c.get('url') or c.get('uri', '')}|{c.get('title', 'X投稿')}>"
            for c in citations[:10]
            if c.get("url") or c.get("uri")
        )
        if links:
            body += f"\n\n*参照投稿*\n{links}"

    response = requests.post(
        webhook_url,
        json={"text": body},
        timeout=10,
    )
    response.raise_for_status()
