"""Ask Claude to read new post captions and extract the group-buys (공구) in them.
Results are stored on each post as post["deals"].

Cost savers:
- several posts go into one request (the instructions are sent once per group, not once per post)
- short field names in the answer (output tokens are the expensive part)
- requests go through the Message Batches API (half price). We wait up to ~25 min for the
  batch; anything not finished is collected by the next run.

Env: ANTHROPIC_API_KEY
"""
import json, os, re, sys, time, pathlib, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts.json"
PENDING = ROOT / "data" / "pending_batches.json"
KST = timezone(timedelta(hours=9))
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")
KEY = os.environ["ANTHROPIC_API_KEY"].strip().strip('"\'')
API = "https://api.anthropic.com/v1"
HDR = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
KEYWORDS = ["공구", "공동구매", "오픈", "마감", "구매", "주문", "판매", "리오더", "재입고", "특가", "할인", "링크", "OPEN", "open"]
CATS = ["food", "kids", "beauty", "tech", "living", "fashion", "interior", "pets", "travel", "none"]
GROUP = 8              # posts per request
MAX_CHARS = 3000       # longest caption part we send (90% of posts are under 1,300 chars)
WAIT_MIN = int(os.environ.get("BATCH_WAIT_MIN", "25"))

SYSTEM = f"""You read Korean Instagram posts by influencers and extract group-buy (공구 / 공동구매) deals.
You get several posts, each starting with "### POST <n>".
Return ONLY JSON: {{"r":[{{"n":<post number>,"d":[deal,...]}}, ...]}} with one entry per post (d is [] when the post has no group-buy).
Each deal uses these short keys:
- "p": product name in Korean as the post names it (brand + item, max ~25 chars)
- "z": short Traditional Chinese (Taiwan) product name (max ~14 chars)
- "c": category, one of {CATS}
  (food=食品/保健, kids=育兒/玩具/童書, beauty=美妝/保養, tech=家電/3C, living=生活/廚房/清潔/寢具,
   fashion=服飾/包/鞋, interior=家具/燈/收納, pets=寵物, travel=旅遊/住宿)
- "o": opening date "YYYY-MM-DD" or null; "ot": opening time "HH:MM" (24h, Korea) or null
- "e": closing date "YYYY-MM-DD" or null; "et": closing time "HH:MM" or null
- "k": "open" (live / opens on the date), "preview" (future deal), "extended" (deadline extended), "reminder" (last day / restock)
Omit keys whose value is null. Resolve dates using each post's time (Korea time, year inferred from it).
A post listing several upcoming deals gives several deals. Cooking classes, giveaway-only events and recipes are NOT deals."""

SALE_SYSTEM = """You read Instagram posts from Korean shopping platforms (Gmarket, 11st, Coupang, Olive Young, 29CM, GS SHOP, Lotte ON, Lotte department store/duty free, ...).
You get several posts, each starting with "### POST <n>".
Extract only BIG platform-wide sale events (e.g. 빅스마일데이, 그랜드십일절, 올영세일, 이구위크, 블랙프라이데이, 브랜드위크, 쇼핑 축제) — not single-product ads.
Return ONLY JSON: {"r":[{"n":<post number>,"d":[event,...]}, ...]} (d is [] when none). Each event uses short keys:
"p": event name in Korean, "z": event name in Traditional Chinese (Taiwan), "c": "sale",
"o"/"ot": start date "YYYY-MM-DD" / time, "e"/"et": end date / time, "k": "open" or "preview",
"h": one short Traditional Chinese line with the key discounts/coupons (max ~40 chars).
Omit null keys. Resolve dates using each post's time (Korea time)."""

LONG = {"p": "product_ko", "z": "product_zh", "c": "category", "o": "open", "ot": "open_time",
        "e": "close", "et": "close_time", "k": "kind", "h": "highlight_zh"}

PLATFORMS = set()
try:
    PLATFORMS = set(json.loads((ROOT / "data" / "platforms.json").read_text(encoding="utf-8")).values())
except Exception:
    pass


def http(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HDR, method=method)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(15 * (attempt + 1)); continue
            raise


def post_block(n, post):
    ts = datetime.strptime(post["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(KST)
    cap = post["caption"]
    if len(cap) > MAX_CHARS:  # keep the start and the end, where dates usually are
        cap = cap[:MAX_CHARS - 900] + "\n…\n" + cap[-900:]
    return f"### POST {n}\nPost time (Korea): {ts:%Y-%m-%d %H:%M} ({'월화수목금토일'[ts.weekday()]})\nAccount: @{post['account']}\n{cap}\n"


def make_request(group, sale):
    return {"model": MODEL, "max_tokens": 400 + 350 * len(group),
            "system": SALE_SYSTEM if sale else SYSTEM,
            "messages": [{"role": "user", "content": "\n".join(post_block(i + 1, p) for i, p in enumerate(group))}]}


def apply(text, group):
    """Put the answer onto the posts. Returns how many posts got an answer."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        rows = json.loads(m.group(0))["r"] if m else []
    except (ValueError, KeyError):
        return 0
    done = 0
    for row in rows:
        try:
            post = group[int(row["n"]) - 1]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        deals = []
        for d in row.get("d") or []:
            if isinstance(d, dict):
                d = {LONG.get(k, k): v for k, v in d.items()}
                if d.get("product_ko"):
                    deals.append(d)
        post["deals"], post["parsed"] = deals, True
        post.pop("pending", None)
        done += 1
    return done


def groups_of(todo):
    normal = [p for p in todo if p["account"] not in PLATFORMS]
    sale = [p for p in todo if p["account"] in PLATFORMS]
    out = []
    for lst, is_sale in ((normal, False), (sale, True)):
        for i in range(0, len(lst), GROUP):
            out.append((lst[i:i + GROUP], is_sale))
    return out


def collect(store, pending):
    """Fetch results of earlier batches that have finished."""
    still = []
    for b in pending:
        try:
            info = json.loads(http("GET", f"{API}/messages/batches/{b['id']}"))
        except Exception as e:
            print("batch check failed:", e); still.append(b); continue
        if info.get("processing_status") != "ended":
            still.append(b); continue
        got = 0
        try:
            for line in http("GET", info["results_url"]).decode("utf-8").splitlines():
                if not line.strip(): continue
                r = json.loads(line)
                ids = b["groups"].get(r["custom_id"], [])
                group = [store["posts"][i] for i in ids if i in store["posts"]]
                if r["result"]["type"] == "succeeded":
                    got += apply(r["result"]["message"]["content"][0]["text"], group)
        except Exception as e:
            print("batch results failed:", e)
        # anything without an answer goes back into the queue
        for ids in b["groups"].values():
            for i in ids:
                p = store["posts"].get(i)
                if p and not p.get("parsed"):
                    p.pop("pending", None)
        print(f"batch {b['id']}: {got} posts read")
    return still


def run_direct(groups):
    for g, sale in groups:
        try:
            msg = json.loads(http("POST", f"{API}/messages", make_request(g, sale)))
            n = apply(msg["content"][0]["text"], g)
            print(f"direct: {n}/{len(g)} posts read")
        except Exception as e:
            print("direct request failed, will retry next run:", e, file=sys.stderr)


def save(store, pending):
    POSTS.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    PENDING.write_text(json.dumps(pending, indent=1), encoding="utf-8")


def main():
    store = json.loads(POSTS.read_text(encoding="utf-8"))
    pending = json.loads(PENDING.read_text()) if PENDING.exists() else []
    # batches older than a day have expired; their posts go back into the queue
    now = datetime.now(timezone.utc)
    for b in pending:
        if now - datetime.fromisoformat(b["created"]) > timedelta(hours=26):
            for ids in b["groups"].values():
                for i in ids:
                    if i in store["posts"]: store["posts"][i].pop("pending", None)
    pending = [b for b in pending if now - datetime.fromisoformat(b["created"]) <= timedelta(hours=26)]
    pending = collect(store, pending)

    # posts older than 14 days are almost always about finished deals: skip them
    cutoff = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%S")
    todo = []
    for p in store["posts"].values():
        if p.get("parsed") or p.get("pending"):
            continue
        if p["timestamp"][:19] < cutoff or not p["caption"].strip() or \
           (p["account"] not in PLATFORMS and not any(k in p["caption"] for k in KEYWORDS)):
            p["deals"], p["parsed"] = [], True
            continue
        todo.append(p)
    groups = groups_of(todo)
    print(f"{len(todo)} posts to read in {len(groups)} requests")

    if groups:
        reqs, gmap = [], {}
        for n, (g, sale) in enumerate(groups):
            cid = f"g{n}_{int(time.time())}"
            reqs.append({"custom_id": cid, "params": make_request(g, sale)})
            gmap[cid] = [p["id"] for p in g]
        try:
            info = json.loads(http("POST", f"{API}/messages/batches", {"requests": reqs}))
            for g, _ in groups:
                for p in g: p["pending"] = info["id"]
            pending.append({"id": info["id"], "created": now.isoformat(), "groups": gmap})
            print("batch submitted:", info["id"])
        except Exception as e:
            print("batch submit failed, reading directly instead:", e)
            run_direct(groups)
    save(store, pending)

    # wait a while for the batch so results show up in this run
    deadline = time.time() + WAIT_MIN * 60
    while pending and time.time() < deadline:
        time.sleep(45)
        before = len(pending)
        pending = collect(store, pending)
        if len(pending) < before:
            save(store, pending)
    save(store, pending)
    print(f"{len(pending)} batch(es) still processing, the next run will collect them")


if __name__ == "__main__":
    main()
