#!/usr/bin/env python3
"""RSS-only Market Radar for WhatsApp.

Design constraints from Uriel:
- RSS only: no YouTube, no independent stock scanning.
- Run on the same clock cadence as Options Radar.
- Send Hebrew summaries to the dedicated WhatsApp group.
- Do not spam: if no high-value new RSS items, send nothing.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time as time_mod
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

WHATSAPP_TARGET = os.environ.get("MARKET_RADAR_WHATSAPP_TARGET", "")
STATE_PATH = Path(os.environ.get("MARKET_RADAR_STATE_PATH", "output/market_radar_state.json"))
LOG_PATH = Path(os.environ.get("MARKET_RADAR_LOG_PATH", "output/market_radar_cron.log"))

FEEDS = [
    {
        "name": "Bloomberg Markets",
        "url": "https://feeds.bloomberg.com/markets/news.rss",
        "tier": 3,
    },
    {
        "name": "CNBC Markets",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "tier": 2,
    },
    {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/rss/topstories",
        "tier": 2,
    },
    {
        "name": "Benzinga",
        "url": "https://www.benzinga.com/feed",
        "tier": 3,
    },
]

# English keyword -> Hebrew reason. Kept intentionally broad but weighted.
KEYWORDS = [
    (r"\bpre[- ]?market\b|premarket", 4, "Premarket / opening move"),
    (r"\bmarket movers?\b|\bmovers\b|\bwhy .* moving\b", 4, "Market mover / catalyst"),
    (r"\bearnings?\b|\breports? results\b|\bquarter\b|\bguidance\b", 3, "Earnings / guidance"),
    (r"\bupgrade[sd]?\b|\bdowngrade[sd]?\b|price target|analyst", 3, "Analyst action / price target"),
    (r"\bFed\b|Federal Reserve|Powell|rate cut|interest rates?|Treasur(?:y|ies)|yields?", 3, "Macro / rates / bonds"),
    (r"\bAI\b|artificial intelligence|data center|datacenter|semiconductor|chip|Nvidia|Broadcom", 3, "AI / data centers / chips"),
    (r"cybersecurity|cyber|ransomware|cloud security", 2, "Cybersecurity"),
    (r"oil|crude|\bIran\b|\bIsrael\b|tariff|trade war|geopolitical|\bwar\b", 3, "Geopolitics / commodities"),
    (r"stocks? rise|stocks? fall|Nasdaq|S&P 500|Dow Jones|futures", 2, "Market direction / indices"),
    (r"options?|unusual options|volatility|VIX", 3, "Options / volatility"),
]

WATCH_TICKERS = {
    "NVDA", "AVGO", "DELL", "HPE", "SNOW", "PLTR", "RBRK", "CRWD", "PANW", "GTLB", "ORCL", "ADBE",
    "AMD", "MU", "MRVL", "ARM", "TSM", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AAPL",
    "RKLB", "LUNR", "ASTS", "RDW", "SPCE", "SATL", "SIDU", "MNTS", "OKLO", "SMR", "NNE", "IONQ",
    "HOOD", "COIN", "MSTR", "RDDT", "APP", "DDOG", "NET", "ZS", "OKTA", "NTAP", "CRM", "NOW", "TEAM",
}

@dataclass
class Item:
    source: str
    title: str
    link: str
    description: str
    published: str
    guid: str
    score: int = 0
    reasons: list[str] | None = None
    tickers: list[str] | None = None


def log(msg: str) -> None:
    ts = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def run(cmd: list[str], timeout: int = 120) -> str:
    cmd = list(cmd)
    if cmd and cmd[0] == "wacli":
        cmd[0] = "/opt/homebrew/bin/wacli"
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT={p.stdout}\nSTDERR={p.stderr}")
    return p.stdout


def market_window_ok(now: datetime | None = None, enforce: bool = True) -> tuple[bool, datetime]:
    now = now or datetime.now(ZoneInfo("America/New_York"))
    if not enforce:
        return True, now
    if now.weekday() >= 5:
        return False, now
    # Same effective Options Radar window: launch wrapper gates 16:05..22:35 Israel,
    # and this prevents holiday/off-hour style spam at script level too.
    return time(9, 0) <= now.time() <= time(16, 0), now


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 OpenClaw MarketRadar/1.0 (+rss)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def strip_html(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def child_text(el: ET.Element, name: str) -> str:
    # Works with namespaces by suffix match.
    for c in list(el):
        if c.tag.lower().endswith(name.lower()):
            return "".join(c.itertext()).strip()
    return ""


def parse_feed(source: str, raw: bytes) -> list[Item]:
    root = ET.fromstring(raw)
    entries = []
    # RSS items or Atom entries.
    for el in root.iter():
        tag = el.tag.lower()
        if tag.endswith("item") or tag.endswith("entry"):
            title = strip_html(child_text(el, "title"))
            desc = strip_html(child_text(el, "description") or child_text(el, "summary") or child_text(el, "content"))
            link = child_text(el, "link")
            if not link:
                for c in list(el):
                    if c.tag.lower().endswith("link"):
                        link = c.attrib.get("href", "") or (c.text or "")
                        break
            guid = child_text(el, "guid") or child_text(el, "id") or link or title
            pub = child_text(el, "pubDate") or child_text(el, "published") or child_text(el, "updated")
            entries.append(Item(source=source, title=title, description=desc, link=link, published=pub, guid=guid))
    return entries


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"seen": {}, "sent": []}


def save_state(state: dict) -> None:
    # Keep only recent-ish seen ids to avoid unbounded growth.
    seen = state.get("seen", {})
    if len(seen) > 3000:
        items = sorted(seen.items(), key=lambda kv: kv[1])[-2000:]
        state["seen"] = dict(items)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def item_id(item: Item) -> str:
    base = f"{item.source}|{item.guid or item.link or item.title}"
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def extract_tickers(text: str) -> list[str]:
    found = set(re.findall(r"\$([A-Z]{1,5})\b", text))
    # Also catch bare watchlist tickers only, to avoid random all-caps words.
    words = set(re.findall(r"\b[A-Z]{2,5}\b", text))
    found |= (words & WATCH_TICKERS)
    return sorted(found)


def score_item(item: Item, source_tier: int) -> Item:
    text = f"{item.title} {item.description}"
    score = source_tier
    reasons = []
    for pat, pts, reason in KEYWORDS:
        if re.search(pat, text, flags=re.I):
            score += pts
            if reason not in reasons:
                reasons.append(reason)
    tickers = extract_tickers(text)
    if tickers:
        score += min(4, len(tickers))
        reasons.append("Relevant tickers")
    # Penalize generic/personal finance noise.
    if re.search(r"retire|retirement|net worth|mortgage|credit card|personal finance|social security|crypto price prediction|price prediction:|\b2025, 2026, 2030\b", text, flags=re.I):
        score -= 7
    item.score = score
    item.reasons = reasons[:4]
    item.tickers = tickers[:8]
    return item


def source_tier(name: str) -> int:
    for f in FEEDS:
        if f["name"] == name:
            return int(f.get("tier", 1))
    return 1


STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "as", "by",
    "from", "after", "before", "amid", "over", "under", "into", "at", "is", "are",
    "stock", "stocks", "market", "markets", "shares", "share", "today", "news", "update",
}


def title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9]+", (title or "").lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def looks_duplicate(a: Item, b: Item) -> bool:
    # Exact URL/guid match first.
    if a.link and b.link and a.link == b.link:
        return True
    if a.guid and b.guid and a.guid == b.guid:
        return True

    ta, tb = title_tokens(a.title), title_tokens(b.title)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    union_overlap = len(ta & tb) / max(1, len(ta | tb))
    # Same story across feeds often has slightly different headline wording.
    return overlap >= 0.72 or union_overlap >= 0.55


def better_item(a: Item, b: Item) -> Item:
    # Prefer the item with richer text, then higher score/source tier.
    key_a = (len(a.description or ""), a.score or 0, source_tier(a.source))
    key_b = (len(b.description or ""), b.score or 0, source_tier(b.source))
    return a if key_a >= key_b else b


def dedupe_items(candidates: list[Item]) -> list[Item]:
    selected: list[Item] = []
    for item in candidates:
        replaced = False
        for idx, existing in enumerate(selected):
            if looks_duplicate(item, existing):
                selected[idx] = better_item(existing, item)
                replaced = True
                break
        if not replaced:
            selected.append(item)
    return selected


def choose_items(items: Iterable[Item], seen: dict) -> list[Item]:
    candidates = []
    for item in items:
        iid = item_id(item)
        if iid in seen:
            continue
        item = score_item(item, source_tier(item.source))
        # Keep quality filtering, but do NOT cap by source.
        # Take all new meaningful items across all RSS sources, then dedupe duplicate stories.
        if item.score >= 7:
            candidates.append(item)

    candidates.sort(key=lambda x: x.score, reverse=True)
    deduped = dedupe_items(candidates)
    deduped.sort(key=lambda x: x.score, reverse=True)
    return deduped


def clean_summary_text(text: str, title: str = "") -> str:
    text = strip_html(text or "")
    text = re.sub(r"\[\.\.\.\]|\s*Continue Reading.*$", " ", text, flags=re.I)
    text = re.sub(r"Advertisement|Read more|Click here", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -—\n\t")
    # If the RSS description is empty or just repeats the headline, fall back to title.
    if not text or (title and text.lower() == title.lower()):
        text = title
    # Keep WhatsApp concise but useful; no need to open links for the core point.
    if len(text) > 360:
        cut = text[:360]
        last_period = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(" — "))
        text = (cut[:last_period + 1] if last_period > 180 else cut).rstrip() + "…"
    return text


def implication_for(item: Item) -> str:
    reasons = item.reasons or []
    tickers = item.tickers or []
    if any("AI" in r for r in reasons):
        return "Potential read-through for AI infrastructure, data-center, chip, and software names trading on the same narrative."
    if any("Macro" in r for r in reasons):
        return "Can affect broad risk appetite through rates, bonds, yields, and macro positioning."
    if any("Earnings" in r for r in reasons):
        return "Useful as a read-through for upcoming earnings, guidance expectations, and sector positioning."
    if any("Geopolitics" in r for r in reasons):
        return "May move oil, yields, defense/energy names, and macro-sensitive sectors."
    if tickers:
        return f"Worth tracking for: {', '.join(tickers[:5])}."
    return "Worth monitoring if it lines up with unusual market or sector movement."


def compose_hebrew(items: list[Item]) -> str:
    il_ts = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%H:%M")
    lines = [f"*Market Radar — RSS Briefs ({il_ts})*", ""]
    for i, item in enumerate(items, 1):
        title = item.title.strip()
        if len(title) > 170:
            title = title[:167] + "…"
        summary = clean_summary_text(item.description, title)
        tickers = f"\nTickers: {', '.join(item.tickers)}" if item.tickers else ""
        reasons = f"\nWhy it matters: {', '.join(item.reasons or [])}" if item.reasons else ""
        implication = implication_for(item)
        lines.append(
            f"{i}) *{item.source}*\n"
            f"Headline: {title}\n"
            f"What happened: {summary}{tickers}{reasons}\n"
            f"Bottom line: {implication}\n"
            f"Source: {item.link}"
        )
        lines.append("")
    lines.append("RSS only — summarized from the feed text. No YouTube and no independent stock scanning.")
    return "\n".join(lines).strip()


def send_whatsapp(message: str) -> None:
    if not WHATSAPP_TARGET:
        log("MARKET_RADAR_WHATSAPP_TARGET is not configured; would have sent message below")
        print(message)
        return
    last_err = None
    for attempt in range(3):
        try:
            run(["wacli", "send", "text", "--to", WHATSAPP_TARGET, "--message", message, "--json"], timeout=120)
            return
        except Exception as e:
            last_err = e
            if "store is locked" not in str(e) or attempt == 2:
                raise
            import time
            time.sleep(5 * (attempt + 1))
    raise last_err


def main() -> int:
    ignore_window = os.environ.get("MARKET_RADAR_IGNORE_MARKET_WINDOW", "0") == "1" or "--ignore-market-window" in sys.argv
    ok, ny_now = market_window_ok(enforce=not ignore_window)
    if not ok:
        log("outside market window; no-op")
        return 0

    state = load_state()
    seen = state.setdefault("seen", {})
    now_int = int(time_mod.time())
    all_items: list[Item] = []
    for feed in FEEDS:
        try:
            raw = fetch(feed["url"])
            parsed = parse_feed(feed["name"], raw)
            all_items.extend(parsed[:20])
            log(f"fetched {feed['name']}: {len(parsed)} items")
        except Exception as e:
            log(f"feed error {feed['name']}: {e}")

    chosen = choose_items(all_items, seen)
    # Mark all fetched item ids as seen, not only sent, to avoid old backlog spam.
    for item in all_items:
        seen[item_id(item)] = now_int

    if not chosen:
        log("no high-value new RSS items; no WhatsApp message")
        save_state(state)
        return 0

    msg = compose_hebrew(chosen)
    send_whatsapp(msg)
    state.setdefault("sent", []).append({"ts": now_int, "count": len(chosen), "titles": [i.title for i in chosen]})
    state["sent"] = state["sent"][-200:]
    save_state(state)
    log(f"sent {len(chosen)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
