**繁體中文** | [English](./README.md)

# /ping-claude — Session 暖機排程器

每天自動在 09:00、14:00、19:00 對 Claude Code 發送 ping，提前啟動 session 計時器，避免在工作中途撞上 5 小時 rate limit。

## 原理

Claude Code 的 session 計時器從你第一次送出訊息時開始。如果太晚才開始，5 小時限制會在最需要的時候到來。這個指令設定 macOS launchd 排程，在固定時間自動送出一個靜默的 `ping`，讓每個時段的計時器準時啟動。

## 使用方式

一次性設定：

```
/ping-claude
```

Claude 會：
1. 建立 `~/scripts/ping-claude.sh` — ping 腳本
2. 安裝 launchd agent 到 `~/Library/LaunchAgents/com.claudecode.ping.plist`
3. 載入並確認運作中

之後不需要任何額外操作。

## 建立的檔案

| 路徑 | 用途 |
|------|------|
| `~/scripts/ping-claude.sh` | 執行 `claude --print "ping"` 並記錄回應 |
| `~/scripts/ping-claude.log` | 所有 ping 嘗試與回應的 log |
| `~/Library/LaunchAgents/com.claudecode.ping.plist` | macOS 排程器（09:00 / 14:00 / 19:00）|

## 自訂排程時間

編輯 plist 來修改觸發時間：

```bash
launchctl unload ~/Library/LaunchAgents/com.claudecode.ping.plist
nano ~/Library/LaunchAgents/com.claudecode.ping.plist
launchctl load ~/Library/LaunchAgents/com.claudecode.ping.plist
```

## 移除

```bash
launchctl unload ~/Library/LaunchAgents/com.claudecode.ping.plist
rm ~/Library/LaunchAgents/com.claudecode.ping.plist
rm ~/scripts/ping-claude.sh
```

## 原始創意

靈感來自 [@maigo.tom](https://www.threads.com/@maigo.tom)
