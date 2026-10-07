# Catch 開起團購雷達

每天自動讀取追蹤的韓國 IG 團購帳號，由 AI 整理出商品、分類、開團／結團日期，做成一個只給自己看的網頁。

## 每天怎麼運作
1. `scripts/fetch.py`：用 Instagram Graph API 讀取 `accounts.txt` 裡每個帳號的最新貼文
2. `scripts/parse.py`：讓 AI 讀新貼文，抽出團購資訊
3. `scripts/build.py`：合併重複的團、只幫還沒結束的團存縮圖，產生網頁
4. GitHub Actions 每天 06:00 和 10:40（韓國時間）自動執行，網頁發佈在 GitHub Pages

## 要追蹤新帳號
編輯 `accounts.txt`，一行一個帳號名稱。

## 需要的 Secrets（Settings → Secrets and variables → Actions）
- `IG_USER_ID`：你的 IG 商業帳號編號
- `FB_TOKEN`：粉專存取權杖（不會過期的那種）
- `ANTHROPIC_API_KEY`：AI 的 API 金鑰
