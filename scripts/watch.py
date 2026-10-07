"""Shared watchlist matching."""
import re, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent

def load():
    f = ROOT / "watchlist.txt"
    items = []
    if not f.exists(): return items
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        aliases = [a.strip() for a in line.split("|") if a.strip()]
        items.append({"label": aliases[0], "aliases": [[w.lower() for w in a.split()] for a in aliases]})
    return items

def norm(s):
    return re.sub(r"\s+", "", (s or "").lower())

def matches(watch, *texts):
    blob = norm(" ".join(t or "" for t in texts))
    return any(all(norm(w) in blob for w in words) for words in watch["aliases"])
