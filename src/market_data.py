"""株価時系列(OHLCV)を yfinance で取得し、テクニカル指標を計算する。

スナップショットしか無かった銘柄に「出遅れ度」を定量化する材料を与える。
LLM不要・API課金なし（yfinance は無料。非公式ライブラリのため稀に失敗する点に注意）。

JPコード(4桁数字 or 5文字英数) → "<code>.T"、米国ティッカーはそのまま。
"""
import re

import yfinance as yf

JP_RE = re.compile(r"^[0-9][0-9A-Z]{3,4}$")


def to_ticker(code: str) -> str:
    code = code.upper()
    return f"{code}.T" if JP_RE.match(code) else code


def get_history(code: str, period: str = "6mo"):
    """OHLCV の DataFrame を返す。失敗時は None。"""
    try:
        df = yf.Ticker(to_ticker(code)).history(period=period, auto_adjust=True)
        return df if df is not None and len(df) else None
    except Exception:
        return None


def technicals(code: str, period: str = "6mo") -> dict:
    """主要テクニカルを計算して返す。取得不可なら空 dict。

    返り値キー: price, ma25_dev_pct, ma75_dev_pct, rsi14,
                from_high_pct(期間高値からの乖離,負=高値より下),
                ret_5d_pct, ret_20d_pct, vol_spike(直近出来高/25日平均)
    """
    df = get_history(code, period)
    if df is None or len(df) < 30:
        return {}

    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float)
    last = float(close.iloc[-1])
    if last <= 0:
        return {}

    ma25 = float(close.tail(25).mean())
    ma75 = float(close.tail(75).mean()) if len(close) >= 75 else None
    high = float(close.max())

    # RSI(14) Wilder簡易（直近14本の平均利得/平均損失）
    delta = close.diff().dropna()
    up = float(delta.clip(lower=0).tail(14).mean())
    down = float((-delta.clip(upper=0)).tail(14).mean())
    rsi = 100.0 if down == 0 else round(100 - 100 / (1 + up / down), 1)

    vol_avg = float(vol.tail(25).mean())
    vol_last = float(vol.iloc[-1])

    def ret(n):
        return round((last / float(close.iloc[-(n + 1)]) - 1) * 100, 1) if len(close) > n else None

    return {
        "price": round(last, 1),
        "ma25_dev_pct": round((last - ma25) / ma25 * 100, 1),
        "ma75_dev_pct": round((last - ma75) / ma75 * 100, 1) if ma75 else None,
        "rsi14": rsi,
        "from_high_pct": round((last - high) / high * 100, 1),
        "ret_5d_pct": ret(5),
        "ret_20d_pct": ret(20),
        "vol_spike": round(vol_last / vol_avg, 2) if vol_avg else None,
    }


def current_price(code: str) -> float | None:
    """直近終値のみ取得（フィードバックのリターン計算用）。"""
    df = get_history(code, period="5d")
    if df is None or not len(df):
        return None
    return round(float(df["Close"].iloc[-1]), 2)
