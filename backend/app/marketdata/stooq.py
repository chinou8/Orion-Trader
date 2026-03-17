import csv
from dataclasses import dataclass
from io import StringIO
from urllib.request import urlopen

try:
    import yfinance as yf
    _YFINANCE_AVAILABLE = True
except ImportError:
    _YFINANCE_AVAILABLE = False


@dataclass
class StooqBar:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_stooq_daily(symbol: str) -> tuple[list[StooqBar], str | None, list[str], str | None]:
    errors: list[str] = []
    for candidate in stooq_symbol_candidates(symbol):
        url = f"https://stooq.com/q/d/l/?s={candidate}&i=d"
        try:
            with urlopen(url, timeout=10) as response:
                raw = response.read().decode("utf-8", errors="ignore")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{candidate}: {exc}")
            continue

        bars = parse_stooq_csv(raw)
        if bars:
            return bars, candidate, errors, None

        errors.append(f"{candidate}: empty response")

    # Fallback: yfinance for .PA and other tickers not covered by stooq
    if _YFINANCE_AVAILABLE:
        bars = _fetch_yfinance(symbol)
        if bars:
            return bars, symbol.upper(), errors, None

    return [], None, errors, "no_data"


def _fetch_yfinance(symbol: str) -> list[StooqBar]:
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y", interval="1d", auto_adjust=True)
        if df.empty:
            return []
        bars: list[StooqBar] = []
        for ts, row in df.iterrows():
            bars.append(StooqBar(
                ts=str(ts.date()),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume") or 0),
            ))
        return bars
    except Exception:
        return []


def stooq_symbol_candidates(symbol: str) -> list[str]:
    s = symbol.strip().upper()
    candidates: list[str] = []
    if s.endswith(".PA"):
        base = s[:-3].lower()
        candidates.extend([f"{base}.fr", base, s.lower()])
    else:
        candidates.append(s.lower())

    # keep order, remove duplicates
    dedup: list[str] = []
    for candidate in candidates:
        if candidate not in dedup:
            dedup.append(candidate)
    return dedup


def parse_stooq_csv(raw_csv: str) -> list[StooqBar]:
    if not raw_csv.strip() or "No data" in raw_csv:
        return []

    bars: list[StooqBar] = []
    reader = csv.DictReader(StringIO(raw_csv))
    for row in reader:
        try:
            ts = (row.get("Date") or "").strip()
            if not ts:
                continue
            bars.append(
                StooqBar(
                    ts=ts,
                    open=float(row.get("Open") or 0),
                    high=float(row.get("High") or 0),
                    low=float(row.get("Low") or 0),
                    close=float(row.get("Close") or 0),
                    volume=float(row.get("Volume") or 0),
                )
            )
        except ValueError:
            continue

    return bars
