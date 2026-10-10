"""Grow the account list from inside the data we already have:
group-buy posts often @mention other group-buy accounts. Accounts mentioned in deal posts by
at least 2 different tracked accounts are added to accounts_auto.txt (max ADD_PER_DAY a day,
never past MAX_ACCOUNTS in total)."""
import json, re, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADD_PER_DAY = 10
MAX_ACCOUNTS = 1200

def read(path):
    p = ROOT / path
    if not p.exists(): return []
    return [l.strip().lstrip("@").lower() for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]

def main():
    manual, auto = read("accounts.txt"), read("accounts_auto.txt")
    blocked = set(read("accounts_blocked.txt"))
    tracked = set(manual) | set(auto) | set(read("accounts_home.txt"))
    if len(tracked) >= MAX_ACCOUNTS:
        print("account list is full"); return
    store = json.loads((ROOT / "data" / "posts.json").read_text(encoding="utf-8"))
    who = collections.defaultdict(set)
    for p in store["posts"].values():
        if not p.get("deals"): continue
        for m in set(re.findall(r"@([A-Za-z0-9._]{3,30})", p["caption"])):
            m = m.lower().rstrip(".")
            if m not in tracked and m not in blocked and m != p["account"]:
                who[m].add(p["account"])
    ranked = sorted((u for u, s in who.items() if len(s) >= 2), key=lambda u: -len(who[u]))
    room = min(ADD_PER_DAY, MAX_ACCOUNTS - len(tracked))
    new = ranked[:room]
    if new:
        f = ROOT / "accounts_auto.txt"
        head = "" if f.exists() else "# 自動從團購貼文的 @提及 加入的帳號。不想要的帳號請移到 accounts_blocked.txt\n"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(head + "".join(u + "\n" for u in new))
    print(f"added {len(new)}: {new}")
    # also pick up accounts found by the 09pangpang search that are not tracked yet
    disc = ROOT / "data" / "discovered_09pangpang.json"
    if disc.exists():
        tracked |= set(new)
        found = json.loads(disc.read_text(encoding="utf-8"))
        extra = [u for u, c in sorted(found.items(), key=lambda x: -x[1]) if u not in tracked and u not in blocked]
        extra = extra[:max(0, MAX_ACCOUNTS - len(tracked))]
        if extra:
            with (ROOT / "accounts.txt").open("a", encoding="utf-8") as fh:
                fh.write("# --- 自動加入：09pangpang 新找到的帳號 ---\n" + "".join(u + "\n" for u in extra))
        print(f"added from 09pangpang: {len(extra)}")

if __name__ == "__main__":
    main()
