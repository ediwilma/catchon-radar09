"""Ask Claude to read each new post caption and extract the group-buys (공구) in it.
Results are stored on each post as post["deals"].

Env: ANTHROPIC_API_KEY
"""
import json, os, re, sys, time, pathlib, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts.json"
KST = timezone(timedelta(hours=9))
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")
KEY = os.environ["ANTHROPIC_API_KEY"].strip().strip('"\'')
KEYWORDS = ["공구", "공동구매", "오픈", "마감", "구매", "주문", "판매", "리오더", "재입고", "특가", "할인", "링크", "OPEN", "open"]
CATS = ["food", "kids", "beauty", "tech", "living", "fashion", "interior", "pets", "travel", "none"]

SYSTEM = f"""You read Korean Instagram posts by influencers and extract group-buy (공구 / 공동구매) deals.
Return ONLY a JSON object: {{"deals": [...]}}. If the post announces no group-buy, return {{"deals": []}}.
Each deal:
- "product_ko": short product name in Korean as the post names it (brand + item, max ~25 chars)
- "product_zh": short Traditional Chinese (Taiwan) name for the product (max ~14 chars)
- "category": one of {CATS}
  (food=食品/保健, kids=育兒/玩具/童書, beauty=美妝/保養, tech=家電/3C, living=生活/廚房/清潔/寢具,
   fashion=服飾/包/鞋, interior=家具/燈/收納, pets=寵物, travel=旅遊/住宿)
- "open": opening date "YYYY-MM-DD" or null if not stated
- "open_time": "HH:MM" 24h Korea time or null
- "close": closing date "YYYY-MM-DD" or null
- "close_time": "HH:MM" or null
- "kind": "open" (deal is live/opens on the date), "preview" (announces a future deal), "extended" (deadline extended), "reminder" (last day / restock of an existing deal)
Rules: resolve dates using the post time given (Korea time, year inferred from it).
A post listing several upcoming deals → several entries. Cooking classes, giveaways-only events and recipes are NOT deals.
"""

SALE_SYSTEM = """You read Instagram posts from Korean shopping platforms (Gmarket, 11st, Coupang, Olive Young, 29CM, GS SHOP, Lotte ON, Lotte department store/duty free, ...).
Extract only BIG platform-wide sale events (e.g. 빅스마일데이, 그랜드십일절, 올영세일, 이구위크, 블랙프라이데이, 브랜드위크, 쇼핑 축제) — not single-product ads.
Return ONLY JSON: {"deals": [...]} (empty list if none). Each item:
- "product_ko": event name in Korean as written (max ~25 chars)
- "product_zh": event name in Traditional Chinese (Taiwan), short
- "category": "sale"
- "open": start date "YYYY-MM-DD" or null; "open_time": "HH:MM" or null
- "close": end date "YYYY-MM-DD" or null; "close_time": "HH:MM" or null
- "kind": "open" or "preview"
- "highlight_zh": one short Traditional Chinese line with the key discounts/coupons (max ~40 chars)
Resolve dates using the post time given (Korea time)."""
PLATFORMS = set()
try:
    PLATFORMS = set(json.loads((ROOT / "data" / "platforms.json").read_text(encoding="utf-8")).values())
except Exception:
    pass

def ask(post):
    ts = datetime.strptime(post["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(KST)
    user = f"Post time (Korea): {ts:%Y-%m-%d %H:%M} ({'월화수목금토일'[ts.weekday()]})\nAccount: @{post['account']}\n\nCaption:\n{post['caption'][:6000]}"
    body = json.dumps({
        "model": MODEL, "max_tokens": 1200, "system": SALE_SYSTEM if post["account"] in PLATFORMS else SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                text = json.load(r)["content"][0]["text"]
            m = re.search(r"\{.*\}", text, re.S)
            deals = json.loads(m.group(0))["deals"] if m else []
            return [d for d in deals if isinstance(d, dict) and d.get("product_ko")]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 529) and attempt < 3:
                time.sleep(10 * (attempt + 1)); continue
            raise
        except (ValueError, KeyError):
            return []
    return []

def main():
    store = json.loads(POSTS.read_text(encoding="utf-8"))
    # posts older than 14 days are almost always about finished deals: skip them to save AI cost
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")
    for p in store["posts"].values():
        if not p.get("parsed") and p["timestamp"][:19] < cutoff:
            p["deals"], p["parsed"] = [], True
    todo = [p for p in store["posts"].values() if not p.get("parsed")]
    print(f"{len(todo)} posts to read")
    for i, p in enumerate(todo, 1):
        # cheap pre-filter: posts with no sales words never go to the AI
        if not p["caption"].strip() or (p["account"] not in PLATFORMS and not any(k in p["caption"] for k in KEYWORDS)):
            p["deals"], p["parsed"] = [], True
            continue
        try:
            p["deals"] = ask(p)
            p["parsed"] = True
            print(f"[{i}/{len(todo)}] @{p['account']}: {len(p['deals'])} deal(s)")
        except Exception as e:
            print(f"[{i}/{len(todo)}] @{p['account']}: failed ({e}), will retry next run", file=sys.stderr)
        if i % 20 == 0:  # save progress
            POSTS.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    POSTS.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")

if __name__ == "__main__":
    main()
