"""SQLite 履歴DB: 適時開示と日次株価スナップショットを蓄積する。

将来のバックテスト・重複排除・トレンド検出の土台。stdlib sqlite3 のみで外部依存なし。
集計確認: python -m src.db
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
DB_PATH = Path(__file__).parent.parent / "stock_history.db"


@contextmanager
def _db():
    """接続を開き、終了時にコミットして必ずクローズする。

    （`with sqlite3.connect()` はコミットするが接続を閉じない点に注意）
    """
    c = sqlite3.connect(DB_PATH)
    try:
        c.execute(
            "CREATE TABLE IF NOT EXISTS disclosures("
            "date TEXT, code TEXT, name TEXT, category TEXT, title TEXT,"
            "UNIQUE(date, code, title))"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS prices("
            "date TEXT, code TEXT, close REAL, UNIQUE(date, code))"
        )
        yield c
        c.commit()
    finally:
        c.close()


def _today() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def save_disclosures(items: list[dict]) -> int:
    """重要開示を保存（重複は無視）。新規挿入件数を返す。"""
    if not items:
        return 0
    today = _today()
    inserted = 0
    with _db() as c:
        before = c.total_changes
        for it in items:
            c.execute(
                "INSERT OR IGNORE INTO disclosures(date,code,name,category,title) VALUES(?,?,?,?,?)",
                (today, it.get("code", ""), it.get("name", ""), it.get("category", ""), it.get("title", "")),
            )
        inserted = c.total_changes - before
    return inserted


def save_prices(price_map: dict) -> int:
    """{code: close} を当日分として保存（重複は無視）。"""
    if not price_map:
        return 0
    today = _today()
    with _db() as c:
        before = c.total_changes
        for code, close in price_map.items():
            if close is None:
                continue
            try:
                c.execute("INSERT OR IGNORE INTO prices(date,code,close) VALUES(?,?,?)", (today, code, float(close)))
            except Exception:
                continue
        return c.total_changes - before


def price_on_or_after(code: str, date: str):
    """指定日以降で最初に記録された (date, close) を返す（バックテスト用）。無ければ None。"""
    with _db() as c:
        return c.execute(
            "SELECT date, close FROM prices WHERE code=? AND date>=? ORDER BY date LIMIT 1",
            (code, date),
        ).fetchone()


def stats() -> dict:
    with _db() as c:
        d = c.execute("SELECT COUNT(*) FROM disclosures").fetchone()[0]
        p = c.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        days = c.execute("SELECT COUNT(DISTINCT date) FROM prices").fetchone()[0]
    return {"disclosures": d, "price_rows": p, "price_days": days}


if __name__ == "__main__":
    print(stats())
