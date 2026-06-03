"""xAI API の usage（トークン数・検索ソース数・コスト）を logs/usage.jsonl に記録する。

各 API レスポンスの `usage` から以下を抽出:
  - input_tokens / output_tokens
  - num_sources_used  ← Live Search の課金ソース数（コストの本体）
  - cost_in_usd_ticks ← xAI が返す生コスト値
推定コストは公表レート（トークン＋$0.025/ソース）から自前計算する（透明性のため）。

集計: python -m src.usage_log   （logs/usage.jsonl を日別・ラベル別に集計表示）
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
LOG_PATH = Path(__file__).parent.parent / "logs" / "usage.jsonl"

# 公表レート (USD / 100万トークン)。コスト推定用。
RATES = {
    "grok-3": (3.0, 15.0),
    "grok-3-mini": (0.30, 0.50),
    "grok-4": (3.0, 15.0),
}
SOURCE_COST = 0.025  # Live Search: $0.025 / source


def _estimate_cost(model: str, in_tok: int, out_tok: int, sources: int) -> float:
    in_rate, out_rate = RATES.get(model, RATES["grok-3"])
    return round(in_tok / 1e6 * in_rate + out_tok / 1e6 * out_rate + sources * SOURCE_COST, 6)


def record(label: str, model: str, data: dict) -> dict:
    """API レスポンスから usage を抽出して 1 行追記。失敗しても本処理は止めない。"""
    u = (data or {}).get("usage") or {}
    in_tok = u.get("input_tokens") or 0
    out_tok = u.get("output_tokens") or 0
    sources = u.get("num_sources_used") or 0
    entry = {
        "ts": datetime.now(JST).isoformat(timespec="seconds"),
        "label": label,
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "num_sources_used": sources,
        "cost_usd_est": _estimate_cost(model, in_tok, out_tok, sources),
        "cost_ticks": u.get("cost_in_usd_ticks"),
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def summarize() -> str:
    if not LOG_PATH.exists():
        return "usage.jsonl がありません（まだ記録なし）"
    rows = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    if not rows:
        return "記録なし"

    by_date: dict[str, dict] = {}
    by_label: dict[str, dict] = {}
    for r in rows:
        d = r["ts"][:10]
        for bucket, key in ((by_date, d), (by_label, r["label"])):
            b = bucket.setdefault(key, {"n": 0, "src": 0, "cost": 0.0})
            b["n"] += 1
            b["src"] += r.get("num_sources_used") or 0
            b["cost"] += r.get("cost_usd_est") or 0.0

    lines = ["=== 日別 ==="]
    for d in sorted(by_date):
        b = by_date[d]
        lines.append(f"  {d}: {b['n']}コール / {b['src']}ソース / 推定 ${b['cost']:.3f}")
    lines.append("=== ラベル別（累計） ===")
    for lab in sorted(by_label, key=lambda k: -by_label[k]["cost"]):
        b = by_label[lab]
        lines.append(f"  {lab:18s}: {b['n']}コール / {b['src']}ソース / 推定 ${b['cost']:.3f}")
    total = sum(r.get("cost_usd_est") or 0.0 for r in rows)
    days = len(by_date)
    lines.append(f"=== 合計 推定 ${total:.3f}（{days}日, 1日平均 ${total/days:.3f} → 月換算 ${total/days*30:.2f}）")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summarize())
