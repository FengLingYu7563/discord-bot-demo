# FengLingYu-game_bot — CLAUDE.md

## 專案入口
專案名稱：FengLingYu-game_bot
專案用途：Python Discord Bot，支援 AI 聊天（Gemini/OpenAI）、音樂播放、Toram Online 遊戲資訊、Minecraft 控制
主要工作目錄：D:\coding\20260517 dcbot\FengLingYu-game_bot
GitHub repo：https://github.com/FengLingYu7563/FengLingYu-game_bot
預設 branch：main

## 專案結構
- `main.py` — 入口點，Bot 初始化、extension 載入、uptime 追蹤
- `config.py` — 環境變數載入
- `database.py` — Firestore 資料庫操作（非 SQLite）
- `chat/gemini_api.py` — Gemini AI 聊天模組
- `chat/openai_api.py` — OpenAI GPT 聊天模組
- `slash/chat/` — AI 聊天相關斜線指令
- `slash/music/music_player.py` — 音樂播放器
- `slash/mc/minecraft_control.py` — Minecraft 控制
- `slash/info/` — 遊戲資訊查詢（Toram boss 等）
- `slash/help/` — 幫助指令
- `slash/ping_command.py` — Ping 指令
- `data/boss.csv` — Toram Online boss 資料
- `data/system_rule.txt` — AI 系統提示詞（.gitignore 保護，不進版本控制）
- `data/keyword_list.txt` — Prompt Injection 過濾清單
- `requirements.txt` — Python 套件依賴
- `Dockerfile` — 容器化設定

## 環境變數（.env）
- `DISCORD_BOT_TOKEN` — Discord Bot Token（必填）
- `GEMINI_API_KEY` — Google Gemini API Key（二選一）
- `OPENAI_API_KEY` — OpenAI API Key（二選一）

## AI 模式選擇邏輯
開機時自動判斷：有 OPENAI_API_KEY 優先用 GPT-4o-mini，否則用 Gemini

## Obsidian 對應筆記
Obsidian vault：未使用
專案駕駛艙：未使用

## 同步規則
開工時：讀本檔、檢查 Git 狀態、不自動 pull/commit/push
收工時：整理進度/待辦/重要決策到本檔、必要時 commit + push

## 上次做到哪
最後動作：2026-05-18 AI 聊天邏輯大幅重構
狀態：已推送至 public repo，等待實機測試回饋

已完成功能：
- 吵架迴圈修正：30分鐘超時 + 機器人對戰最多回覆3次
- 心情系統：屁孩40% / 溫柔35% / 普通25%，20分鐘內連動歷史沿用
- 歷史紀錄：改為一問一答配對 {"user","bot","t"}，20分鐘過期自動清除，上限5則
- 修復 keywords 從未傳入 AI 的 bug
- 新增長期人格觀察 observations 欄位（累積式，跨對話）
- Prompt 改善：temperature 0.85、禁慣用開頭、限制回覆長度1~2句
- 全形括號 （） 過濾修正
- Prompt Injection 過濾清單整合至 keyword_list.txt
- 公開 repo 建立：https://github.com/FengLingYu7563/FengLingYu-game_bot-public

## 待辦事項
- 實機測試：確認心情系統、observations 累積是否正常運作
- 若回覆仍過長，追加 max_tokens 作為硬限制保險

## 重要決策
- commit 不加 Co-Authored-By Claude
- system_rule.txt 不進版本控制（.gitignore 保護）
- 公私 repo 並存：私人 origin + 公開 public remote
- 機器人對戰結束條件：30分鐘超時 OR 回覆滿3次（二擇一先到先生效）
- 歷史過期時間與心情重置時間統一為 20 分鐘

## 不要做
- 不要把 .env、API key、token 寫進 repo
- 不要自動納入無關 git 變更
- .env 已受 .gitignore 保護且從未被 commit，保持此狀態
