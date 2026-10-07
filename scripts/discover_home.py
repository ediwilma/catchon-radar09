"""Daily: read 09pangpang's home-goods category pages and add any new group-buy accounts
to accounts_home.txt (you lean towards home goods, so these accounts get priority)."""
import re, time, pathlib, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "accounts_home.txt"
CATS = ["home-living", "interior", "furniture", "fabric", "lighting", "decor", "storage", "home-office",
        "living-goods", "kitchen-goods", "bedding-fabric", "cleaning-detergent", "tableware",
        "cleaning-appliances", "kitchen-appliances", "home-appliances", "seasonal-appliances"]
SKIP = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "direct", "09pangpang"}
MAX_TOTAL = 500
UA = {"User-Agent": "Mozilla/5.0 (personal list builder; contact via github.com/ediwilma)"}

def read(name):
    f = ROOT / name
    return [l.strip().lower() for l in f.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")] if f.exists() else []

def main():
    have = set(read("accounts.txt")) | set(read("accounts_auto.txt")) | set(read("accounts_home.txt"))
    blocked = set(read("accounts_blocked.txt"))
    found = []
    for c in CATS:
        try:
            req = urllib.request.Request(f"https://09pangpang.com/category/{c}", headers=UA)
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except Exception as e:
            print(c, e); continue
        users = {u.lower().rstrip(".") for u in re.findall(r"instagram\.com/([A-Za-z0-9._]{2,30})", html)}
        users |= {u.lower().rstrip(".") for u in re.findall(r'title="[^"]*@([A-Za-z0-9._]{2,30})"', html)}
        for u in sorted(users - SKIP):
            if u not in have and u not in blocked and u not in found:
                found.append(u)
        time.sleep(1)
    room = MAX_TOTAL - len(have)
    new = found[:max(0, room)]
    if new:
        head = "" if OUT.exists() else "# 家居用品類團購主（每天從 09pangpang 家居分類自動加入，讀取時優先）\n"
        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(head + "".join(u + "\n" for u in new))
    print(f"home accounts added: {len(new)} {new}")

if __name__ == "__main__":
    main()
