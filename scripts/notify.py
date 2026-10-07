"""Send a phone notification (via the free ntfy app) when a watched product gets a new group-buy.
Env: NTFY_TOPIC (secret topic name you subscribe to in the ntfy app)."""
import json, os, pathlib, urllib.request
from watch import load

ROOT = pathlib.Path(__file__).resolve().parent.parent
SENT = ROOT / "data" / "notified.json"
SITE_URL = "https://ediwilma.github.io/catchon-radar09/"

def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    deals = json.loads((ROOT / "site" / "deals.json").read_text(encoding="utf-8"))
    sent = set(json.loads(SENT.read_text())) if SENT.exists() else set()
    hits = [d for d in deals if d.get("watch") and not d.get("ended")
            and f'{d["id"]}|{d.get("open")}' not in sent]
    print(f"{len(hits)} new watched deal(s)")
    for d in hits:
        when = f'{d["open"][5:].replace("-", "/")} 開團' + (f' ～ {d["close"][5:].replace("-", "/")}' if d.get("close") else "")
        msg = f'{d["kr"]}（{d.get("zh") or ""}）\n@{d["acc"]}・{when}'
        if topic:
            req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode(), headers={
                "Title": f'追蹤商品開團：{d["watch"]}'.encode("utf-8"),
                "Tags": "shopping_bags",
                "Click": d.get("link") or SITE_URL,
                "Priority": "high",
            })
            try:
                urllib.request.urlopen(req, timeout=20)
            except Exception as e:
                print("notify failed:", e); continue
        sent.add(f'{d["id"]}|{d.get("open")}')
        print("notified:", msg.replace("\n", " "))
    SENT.write_text(json.dumps(sorted(sent), ensure_ascii=False))

if __name__ == "__main__":
    main()
