"""Fetch the latest posts of every account in accounts.txt via the
Instagram Graph API (Business Discovery) and merge them into data/posts.json.

Env: IG_USER_ID, FB_TOKEN
"""
import json, os, sys, time, pathlib, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
POSTS = ROOT / "data" / "posts.json"
FRESH = ROOT / "data" / "fresh_media.json"   # media urls from this run only (not committed)
API = "https://graph.facebook.com/v26.0"
KEEP_DAYS = 45            # drop posts older than this
PER_ACCOUNT = 12          # newest posts to read per account
PAUSE = float(os.environ.get("PAUSE_SECONDS", "15"))  # stay under ~200 calls/hour

USAGE = {}
RATE_WAIT = 600      # seconds to wait when Meta says "slow down"
RATE_TRIES = 6       # give up after ~1 hour of waiting
IG_USER_ID = os.environ["IG_USER_ID"]
TOKEN = os.environ["FB_TOKEN"]

def accounts():
    out = []
    for line in (ROOT / "accounts.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("@")
        if line and not line.startswith("#") and line not in out:
            out.append(line)
    return out

def discover(username):
    fields = (f"business_discovery.username({username})"
              "{username,name,followers_count,profile_picture_url,"
              f"media.limit({PER_ACCOUNT})"
              "{id,caption,timestamp,permalink,media_type,media_url,thumbnail_url,"
              "children{media_type,media_url,thumbnail_url}}}")
    q = urllib.parse.urlencode({"fields": fields, "access_token": TOKEN})
    with urllib.request.urlopen(f"{API}/{IG_USER_ID}?{q}", timeout=60) as r:
        USAGE["app"] = r.headers.get("X-App-Usage") or USAGE.get("app")
        USAGE["buc"] = r.headers.get("X-Business-Use-Case-Usage") or USAGE.get("buc")
        return json.load(r)["business_discovery"]

def cover_url(m):
    if m.get("media_type") == "VIDEO":
        return m.get("thumbnail_url")
    if m.get("media_type") == "CAROUSEL_ALBUM":
        for c in (m.get("children") or {}).get("data", []):
            u = c.get("thumbnail_url") if c.get("media_type") == "VIDEO" else c.get("media_url")
            if u:
                return u
    return m.get("media_url") or m.get("thumbnail_url")

def main():
    store = json.loads(POSTS.read_text(encoding="utf-8")) if POSTS.exists() else {"accounts": {}, "posts": {}}
    fresh = {}
    names = accounts()
    failed = []
    errors = []
    waits = 0
    ok = 0
    stopped = False
    for i, name in enumerate(names):
        bd = None
        while True:
            try:
                bd = discover(name)
                break
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")[:300]
                limited = any(f'"code":{c},' in body for c in (4, 17, 32, 613)) or "limit reached" in body
                if limited and waits < RATE_TRIES:
                    waits += 1
                    print(f"[wait] Meta rate limit at {name}, waiting {RATE_WAIT//60} min ({waits}/{RATE_TRIES})", file=sys.stderr)
                    time.sleep(RATE_WAIT)
                    continue
                print(f"[skip] {name}: HTTP {e.code} {body}", file=sys.stderr)
                failed.append(name); errors.append({"account": name, "error": f"HTTP {e.code} {body}"})
                if limited:
                    print("Still rate limited — stopping, the rest will be read next run.", file=sys.stderr)
                    stopped = True
                break
            except Exception as e:  # network hiccup
                print(f"[skip] {name}: {e}", file=sys.stderr)
                failed.append(name); errors.append({"account": name, "error": str(e)[:300]})
                break
        if stopped:
            break
        if bd is None:
            continue
        ok += 1
        store["accounts"][name] = {
            "followers": bd.get("followers_count"),
            "name": bd.get("name"),
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        new = 0
        for m in (bd.get("media") or {}).get("data", []):
            pid = m["id"]
            url = cover_url(m)
            if url:
                fresh[pid] = url
            if pid not in store["posts"]:
                new += 1
                store["posts"][pid] = {
                    "id": pid, "account": name,
                    "caption": m.get("caption") or "",
                    "timestamp": m["timestamp"],
                    "permalink": m.get("permalink"),
                    "parsed": False,
                }
        print(f"[ok] {name}: {new} new")
        if i < len(names) - 1:
            time.sleep(PAUSE)

    POSTS.parent.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    store["posts"] = {k: v for k, v in store["posts"].items()
                      if datetime.strptime(v["timestamp"], "%Y-%m-%dT%H:%M:%S%z") >= cutoff}
    POSTS.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    FRESH.write_text(json.dumps(fresh), encoding="utf-8")
    status = {"time": datetime.now(timezone.utc).isoformat(), "ok": ok, "waits": waits, "usage": USAGE,
              "total": len(names), "errors": errors[:10]}
    (ROOT / "data" / "last_run.json").write_text(json.dumps(status, ensure_ascii=False, indent=1).replace(TOKEN, "***"), encoding="utf-8")
    print(f"done: {ok}/{len(names)} accounts, {len(store['posts'])} posts kept")

if __name__ == "__main__":
    main()
