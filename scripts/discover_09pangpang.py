"""One-off: read 09pangpang post pages and collect every Instagram account that ran a group-buy there.
Writes data/discovered_09pangpang.json  {username: number_of_posts}
Run from the 'discover' workflow (GitHub's servers can reach the site)."""
import json, re, sys, time, pathlib, urllib.request, urllib.error, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "discovered_09pangpang.json"
START = int(sys.argv[1]) if len(sys.argv) > 1 else 0
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
DELAY = 0.4          # be gentle with their server
SKIP = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "direct", "09pangpang"}
UA = {"User-Agent": "Mozilla/5.0 (personal list builder; contact via github.com/ediwilma)"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def latest_id():
    html = get("https://09pangpang.com/")
    ids = [int(x) for x in re.findall(r"/post/(\d+)", html)]
    return max(ids)

def main():
    found = collections.Counter(json.loads(OUT.read_text()) if OUT.exists() else {})
    top = START or latest_id()
    print(f"scanning posts {top} down to {top - COUNT + 1}")
    misses = 0
    for pid in range(top, top - COUNT, -1):
        try:
            html = get(f"https://09pangpang.com/post/{pid}")
            misses = 0
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("asked to slow down, pausing 60s"); time.sleep(60)
            misses += 1
            if misses > 200:
                print("200 missing pages in a row, stopping"); break
            continue
        except Exception as e:
            print(f"{pid}: {e}"); time.sleep(5); continue
        users = {u.lower() for u in re.findall(r"instagram\.com/([A-Za-z0-9._]{2,30})", html)} - SKIP
        for u in users:
            found[u.rstrip(".")] += 1
        if pid % 200 == 0:
            print(f"{pid}: {len(found)} accounts so far")
            OUT.write_text(json.dumps(dict(found.most_common()), ensure_ascii=False, indent=0))
        time.sleep(DELAY)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(dict(found.most_common()), ensure_ascii=False, indent=0))
    print(f"done: {len(found)} accounts")

if __name__ == "__main__":
    main()
