"""Turn data/posts.json into the website in site/:
- merges duplicate announcements of the same deal
- downloads a small cover image only for deals that have not ended
- writes site/index.html (data embedded) + site/img/*.webp
"""
import json, re, io, shutil, pathlib, urllib.request
from datetime import datetime, timezone, timedelta
from PIL import Image
import sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from watch import load as load_watch, matches as watch_matches

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).date().isoformat()

def norm(s):
    return re.sub(r"[\s\W_]+", "", s or "").lower()[:10]

def fmt_followers(n):
    if not n: return ""
    return f"{n/10000:.1f}萬".replace(".0萬", "萬") if n >= 10000 else f"{n:,}"

def main():
    store = json.loads((ROOT / "data" / "posts.json").read_text(encoding="utf-8"))
    fresh_path = ROOT / "data" / "fresh_media.json"
    fresh = json.loads(fresh_path.read_text()) if fresh_path.exists() else {}
    deals = {}
    for p in sorted(store["posts"].values(), key=lambda p: p["timestamp"]):
        posted = datetime.strptime(p["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(KST)
        for d in p.get("deals") or []:
            key = p["account"] + "|" + norm(d.get("product_ko"))
            open_ = d.get("open") or (posted.date().isoformat() if d.get("kind") in ("open", "reminder", "extended", None) else None)
            cur = deals.get(key)
            if not cur:
                cur = deals[key] = {
                    "id": key, "acc": p["account"], "kr": d["product_ko"], "zh": d.get("product_zh") or "",
                    "cat": d.get("category") if d.get("category") in
                           ("food","kids","beauty","tech","living","fashion","interior","pets","travel") else "none",
                    "open": open_, "openTime": d.get("open_time"),
                    "close": d.get("close"), "closeTime": d.get("close_time"),
                }
            else:
                # a newer post about the same deal: keep earliest known open, newest close
                if open_ and cur["close"] and open_ > cur["close"]:
                    # previous round already closed: this is a new round (재오픈 / 리오더)
                    cur["open"], cur["openTime"], cur["close"], cur["closeTime"] = open_, d.get("open_time"), None, None
                elif open_ and not cur["open"]:
                    cur["open"], cur["openTime"] = open_, d.get("open_time")
                if d.get("close"):
                    cur["close"], cur["closeTime"] = d["close"], d.get("close_time")
                if d.get("product_zh"): cur["zh"] = d["product_zh"]
            cur["link"] = p.get("permalink")
            cur["post"] = p["id"]
            cur["posted"] = posted.isoformat(timespec="minutes")

    acc_info = store.get("accounts", {})
    out = []
    if SITE.exists(): shutil.rmtree(SITE)
    (SITE / "img").mkdir(parents=True)
    for d in deals.values():
        if not d["open"]:
            d["open"] = d["posted"][:10]
        ended = d["close"] and d["close"] < TODAY
        d["fol"] = fmt_followers((acc_info.get(d["acc"]) or {}).get("followers"))
        d["img"] = None
        url = fresh.get(d["post"])
        if not ended and url:
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    im = Image.open(io.BytesIO(r.read())).convert("RGB")
                im.thumbnail((480, 600))
                name = f"img/{d['post']}.webp"
                im.save(SITE / name, "WEBP", quality=72, method=6)
                d["img"] = name
            except Exception as e:
                print(f"[img] {d['acc']} {d['kr']}: {e}")
        del d["post"]
        out.append(d)
    out.sort(key=lambda d: d["posted"], reverse=True)
    watches = load_watch()
    for d in out:
        d["ended"] = bool(d["close"] and d["close"] < TODAY)
        d["watch"] = next((w["label"] for w in watches if watch_matches(w, d["kr"], d["zh"])), None)
    (SITE / "deals.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    html = (ROOT / "template" / "index.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/[]", json.dumps(out, ensure_ascii=False))
    html = html.replace("/*__WATCH__*/[]", json.dumps([w["label"] for w in watches], ensure_ascii=False))
    html = html.replace("/*__UPDATED__*/\"\"", json.dumps(datetime.now(KST).strftime("%m/%d %H:%M")))
    (SITE / "index.html").write_text(html, encoding="utf-8")
    for f in ("logo.webp", "manifest.json", "sw.js", "icon-192.png", "icon-512.png"):
        shutil.copy(ROOT / "template" / f, SITE / f)
    (SITE / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    print(f"built {len(out)} deals, {sum(1 for d in out if d['img'])} with images")

if __name__ == "__main__":
    main()
