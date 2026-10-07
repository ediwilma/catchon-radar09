"""Once a day: read Korean news + Google Trends (KR) and let Claude pick the PRODUCTS that are
going viral right now. Writes data/trends.json. Env: ANTHROPIC_API_KEY"""
import json, os, re, sys, time, pathlib, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "trends.json"
KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip().strip('"\'')
MODELS = [os.environ.get("TREND_MODEL", "claude-sonnet-5-5"), "claude-haiku-4-5"]
QUERIES = ["품절 대란", "오픈런 신상", "열풍 신제품", "SNS 화제 제품", "완판 신상", "인기 급상승 제품",
           "MZ 인기 간식", "편의점 신상 품절", "다이소 품절", "올리브영 품절", "육아템 인기", "재입고 대란"]
UA = {"User-Agent": "Mozilla/5.0"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()

def news():
    items, seen = [], set()
    for q in QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:7d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        try:
            root = ET.fromstring(get(url))
        except Exception as e:
            print("news fail", q, e); continue
        for it in root.iter("item"):
            t = (it.findtext("title") or "").strip()
            if t in seen: continue
            seen.add(t)
            items.append({"title": t, "link": it.findtext("link"), "date": it.findtext("pubDate")})
        time.sleep(1)
    return items

def google_trends():
    try:
        root = ET.fromstring(get("https://trends.google.com/trending/rss?geo=KR"))
        return [it.findtext("title") for it in root.iter("item")]
    except Exception as e:
        print("trends fail", e); return []

PROMPT = """以下是最近 7 天韓國新聞標題（含連結編號）和 Google 韓國熱門搜尋。
請找出「正在爆紅的商品」：食品、零食、飲料、美妝、生活用品、育兒用品、服飾、3C 等可以買的東西（包含品牌新品、聯名款、便利商店新品）。
不要人物、新聞事件、股票、政治、娛樂節目，也不要只是一般促銷。
同一個商品的多則新聞要合併。依熱度排序，最多 15 個。
只回傳 JSON：{"items":[{"name_ko":"韓文商品名","name_zh":"繁體中文名","brand":"品牌或通路","why_zh":"一兩句繁體中文說明為什麼紅（例如：全國便利商店缺貨、開賣半天售完）","category":"food|beauty|living|kids|fashion|tech|other","keyword":"在 IG 或團購搜尋用的韓文關鍵字（短）","news":[連結編號,...]}]}"""

def main():
    if OUT.exists() and not os.environ.get("FORCE_TRENDS"):
        old = json.loads(OUT.read_text(encoding="utf-8"))
        if datetime.now(timezone.utc) - datetime.fromisoformat(old["updated"]) < timedelta(hours=20):
            print("trends are fresh, skipping"); return
    if not KEY:
        print("no AI key"); return
    n = news()[:220]
    g = google_trends()
    print(f"{len(n)} news, {len(g)} trending searches")
    lines = [f"[{i}] {x['title']}" for i, x in enumerate(n)]
    user = PROMPT + "\n\n# 新聞\n" + "\n".join(lines) + "\n\n# Google 熱門搜尋\n" + "、".join(g)
    text = None
    for model in MODELS:
        body = json.dumps({"model": model, "max_tokens": 4000, "messages": [{"role": "user", "content": user}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                text = json.load(r)["content"][0]["text"]
            break
        except Exception as e:
            print("model", model, "failed:", e)
    if text is None:
        return
    data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    for it in data["items"]:
        it["news"] = [{"title": n[i]["title"], "link": n[i]["link"]} for i in it.get("news", []) if isinstance(i, int) and 0 <= i < len(n)][:4]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).isoformat(), "items": data["items"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(data['items'])} hot products")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("trends skipped:", e)  # never break the daily update
