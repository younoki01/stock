"""Slack Web API クライアント。

Bot Token (xoxb-) を使ってチャンネル履歴の取得とスレッド返信を行う。
必要スコープ: channels:history (public) または groups:history (private), chat:write
"""

import os
import requests

API_BASE = "https://slack.com/api"


def _token() -> str:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN が設定されていません")
    return token


def _post(method: str, payload: dict) -> dict:
    response = requests.post(
        f"{API_BASE}/{method}",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API {method} error: {data.get('error')}")
    return data


def _get(method: str, params: dict) -> dict:
    response = requests.get(
        f"{API_BASE}/{method}",
        headers={"Authorization": f"Bearer {_token()}"},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API {method} error: {data.get('error')}")
    return data


def fetch_channel_history(channel: str, oldest: float | None = None, limit: int = 50) -> list[dict]:
    """指定チャンネルの新しいメッセージを取得（古い順にソートして返す）。

    oldest: この時刻(ts, unix秒)より新しいメッセージのみ。
    """
    params = {"channel": channel, "limit": limit}
    if oldest is not None:
        params["oldest"] = f"{oldest:.6f}"
    data = _get("conversations.history", params)
    messages = data.get("messages", [])
    return sorted(messages, key=lambda m: float(m.get("ts", "0")))


def post_thread_reply(channel: str, thread_ts: str, text: str = "", blocks: list | None = None) -> dict:
    """スレッドに返信する。"""
    payload = {"channel": channel, "thread_ts": thread_ts}
    if blocks:
        payload["blocks"] = blocks
        if text:
            payload["text"] = text  # fallback for notifications
    else:
        payload["text"] = text
    return _post("chat.postMessage", payload)
