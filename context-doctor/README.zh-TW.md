**繁體中文** | [English](./README.md)

# /context-doctor

Claude Code token 使用分析 — 找出 token 花在哪裡，以及如何節省。

---

## 為什麼需要

1M context window 移除了舊的 ~160K 自動壓縮。Session 現在可以不受限制地成長超過 500K。每次 prompt 重送完整 context，500K + 3 tool calls = 一個 prompt 花費 1.5M tokens。大 context 下的 cache miss 成本是原來的 ~10 倍。

---

## 運作方式

**省 token 設計：** 重分析由獨立腳本執行（零 token 消耗）。Agent 只讀取小型 JSON 摘要並給建議。

```
analyze.sh (純 bash)  ->  JSON 摘要  ->  agent 解讀  ->  優化建議
   零 token 消耗          ~500 bytes     最少 token
```

### 組件

| 檔案 | 用途 | 依賴 |
|------|------|------|
| `analyze.sh` | 核心分析 — 解析 JSONL，輸出 JSON | bash + awk（內建） |
| `analyze-visual.py` | 可選圖表產生 | python3 + matplotlib + numpy |
| `context-doctor.md` | Agent 指令（< 50 行） | 無 |

---

## 報告內容

| 指標 | 說明 |
|------|------|
| Context 成長 | 每 session 的平均/最大 context 大小 |
| Sessions > 200K / 400K | 超大 session 數量 |
| Cache 命中率 | 從 cache 服務的 turns 百分比 |
| Cache misses | 次數和估算的額外成本 |
| Token 分類 | Input / output / cache read / cache creation |
| 最貴的 sessions | 按最大 context 大小排序 |

---

## 建議邏輯

| 條件 | 建議 |
|------|------|
| 平均 context > 200K | 更頻繁使用 /clear 或 /last-word |
| 有 sessions > 400K | 將大任務拆分成較小的 sessions |
| Cache 命中率 < 90% | 保持 prompt 間隔在 5 分鐘內 |
| Cache miss 成本高 | 避免 prompt 之間的長時間暫停 |
| Output/input 比例高 | 要求更簡潔的回覆 |

---

## 獨立使用

可以直接執行分析腳本，不需要 Claude Code：

```bash
# JSON 報告（最近 7 天）
bash ~/.claude/commands/context-doctor/analyze.sh 7

# JSON 報告（最近 30 天）
bash ~/.claude/commands/context-doctor/analyze.sh 30

# 視覺化圖表（需要 matplotlib）
python3 ~/.claude/commands/context-doctor/analyze-visual.py 7
```

---

## 安裝

```bash
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote context-doctor
# 或手動
mkdir -p ~/.claude/commands/context-doctor
cp context-doctor.md ~/.claude/commands/context-doctor.md
cp analyze.sh analyze-visual.py ~/.claude/commands/context-doctor/
```

## 使用

在 Claude Code 中輸入：`/context-doctor`

---

## Credits

- [RyanSeanPhillips](https://github.com/RyanSeanPhillips) — 1M context token burn 分析
- [cldctrl](https://github.com/RyanSeanPhillips/cldctrl) — context_analysis.py
