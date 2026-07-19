"""
CORE/ML/SENTIMENT — PEWE Advanced Sentiment Analysis (News RSS + VADER)

Mengapa (instruksi Panji: integrasi berita lebih dalam ke Convinced Score):
  - Fear&Greed (FG) cuma 1 angka makro harian -> terlalu kasar.
  - Berita real-time (CoinDesk/Cointelegraph/Binance RSS, GRATIS, no key)
    kasih sinyal mikro: ada pump/regulasi/FUD/hack? -> score per aset.
  - VADER (lexicon sentiment) -> score headline akurat tanpa ML berat.

Anti-overfit/jujur:
  - RSS gratis, deterministic, no API key, no charge.
  - Bila network gagal -> fallback ke FG (graceful, tdk crash).
  - Filter per-symbol: headline yg sebut nama token -> bobot lebih tinggi.
"""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor

import feedparser
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Feed RSS crypto (gratis, public) — pakai UA browser supaya gak di-403 server
_FEED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PEWE/1.0",
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}
RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://www.binance.com/en/feed-news/rss.xml",
    "https://decrypt.co/feed",
    "https://www.newsbtc.com/feed/",
    "https://bitcoinmagazine.com/.rss/full/",
]
_FEED_CACHE_TTL = 300  # 5 menit cache (hindari spam request)
_cache = {"ts": 0.0, "entries": []}

_SID = SentimentIntensityAnalyzer()

# keyword token -> simbol (untuk filter per-asset)
TOKEN_ALIASES = {
    "BTC": ["bitcoin", "btc"], "ETH": ["ethereum", "eth"], "BNB": ["bnb", "binance coin"],
    "SOL": ["solana", "sol"], "XRP": ["ripple", "xrp"], "ADA": ["cardano", "ada"],
    "DOGE": ["dogecoin", "doge"], "AVAX": ["avalanche", "avax"], "LINK": ["chainlink", "link"],
    "DOT": ["polkadot", "dot"], "MATIC": ["polygon", "matic"], "LTC": ["litecoin", "ltc"],
    "TRX": ["tron", "trx"], "ATOM": ["cosmos", "atom"], "UNI": ["uniswap", "uni"],
    "NEAR": ["near"], "APT": ["aptos", "apt"], "FIL": ["filecoin", "fil"],
    "ARB": ["arbitrum", "arb"], "OP": ["optimism", "op"], "INJ": ["injective", "inj"],
    "SUI": ["sui"], "TIA": ["celestia", "tia"], "SEI": ["sei"], "RNDR": ["render", "rndr"],
    "FET": ["fetch.ai", "fet"], "GRT": ["the graph", "grt"], "ALGO": ["algorand", "algo"],
    "SAND": ["sandbox", "sand"], "AXS": ["axie", "axs"], "THETA": ["theta"],
    "AAVE": ["aave"], "COMP": ["compound", "comp"], "SNX": ["synthetix", "snx"],
}


def _fetch_feed(url: str) -> list:
    try:
        r = requests.get(url, headers=_FEED_HEADERS, timeout=12)
        if r.status_code != 200 or not r.content:
            return []
        d = feedparser.parse(r.content)
        out = []
        for e in d.entries:
            title = e.get("title", "")
            summary = e.get("summary", "") or e.get("description", "")
            out.append((title + " " + summary))
        return out
    except Exception:
        return []


def _fetch_all() -> list:
    """Fetch semua feed (parallel), cache 5 menit."""
    now = time.time()
    if now - _cache["ts"] < _FEED_CACHE_TTL and _cache["entries"]:
        return _cache["entries"]
    texts = []
    with ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as ex:
        for res in ex.map(_fetch_feed, RSS_FEEDS):
            texts.extend(res)
    _cache["ts"] = now
    _cache["entries"] = texts
    return texts


def _vader_score(text: str) -> float:
    """Return -1..1 (VADER compound)."""
    return _SID.polarity_scores(text).get("compound", 0.0)


def news_sentiment(symbol: str = None, force_refresh: bool = False) -> dict:
    """Advanced sentiment dari RSS + VADER.
    Return: {score_0_100, compound_mean, n_articles, n_relevant,
             top_positive, top_negative, symbol, relevant_titles}
    symbol=None -> sentiment market-wide. symbol='BTC' -> filter headline yg sebut BTC.
    """
    texts = _fetch_all() if not force_refresh else ([t for f in RSS_FEEDS for t in _fetch_feed(f)])
    if not texts:
        return {"score_0_100": 50.0, "compound_mean": 0.0, "n_articles": 0,
                "n_relevant": 0, "top_positive": [], "top_negative": [],
                "symbol": symbol, "relevant_titles": [], "source": "empty"}

    aliases = []
    if symbol:
        base = symbol.split("/")[0]
        aliases = TOKEN_ALIASES.get(base, [base.lower()])

    scored = []
    for t in texts:
        tl = t.lower()
        if aliases and not any(a in tl for a in aliases):
            continue  # bukan tentang token ini
        c = _vader_score(t)
        scored.append((t, c))

    if not scored:
        return {"score_0_100": 50.0, "compound_mean": 0.0, "n_articles": len(texts),
                "n_relevant": 0, "top_positive": [], "top_negative": [],
                "symbol": symbol, "relevant_titles": [], "source": "rss_no_match"}

    compounds = [c for _, c in scored]
    mean_c = sum(compounds) / len(compounds)
    score_100 = round((mean_c + 1.0) / 2.0 * 100.0, 1)
    scored.sort(key=lambda x: x[1], reverse=True)
    top_pos = [t[:80] for t, c in scored[:3] if c > 0.05]
    top_neg = [t[:80] for t, c in scored[-3:] if c < -0.05][::-1]
    return {
        "score_0_100": score_100,
        "compound_mean": round(mean_c, 3),
        "n_articles": len(texts),
        "n_relevant": len(scored),
        "top_positive": top_pos,
        "top_negative": top_neg,
        "symbol": symbol,
        "relevant_titles": [t[:120] for t, _ in scored[:5]],
        "source": "rss_vader",
    }


# singleton module buat dipakai orchestrator
_INST = None
def get_sentiment_module():
    global _INST
    if _INST is None:
        _INST = SentimentModule()
    return _INST


class SentimentModule:
    """Thin wrapper supaya orchestrator/pipeline panggil konsisten."""
    def news(self, symbol: str = None, force_refresh: bool = False) -> dict:
        return news_sentiment(symbol, force_refresh)

    def combined(self, fg_value: float, symbol: str = None) -> float:
        """Gabungan FG + News -> 0..1 (bobot 50/50).
        Dipakai di Convinced Score sebagai komponen sentiment."""
        ns = news_sentiment(symbol)
        news_01 = ns["score_0_100"] / 100.0
        fg_01 = (fg_value if fg_value is not None else 50.0) / 100.0
        if ns["n_relevant"] > 0:
            return 0.5 * fg_01 + 0.5 * news_01
        return fg_01  # fallback FG kalau tdk ada berita relevan
