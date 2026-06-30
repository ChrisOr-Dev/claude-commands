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
analyze.sh -> doctor_core.py  ->  JSON 摘要  ->  agent 解讀  ->  優化建議
        零 token 消耗               ~500 bytes     最少 token
```

### 組件

| 檔案 | 用途 | 依賴 |
|------|------|------|
| `analyze.sh` | 精簡包裝 — 執行解析器並輸出 JSON | bash + python3 |
| `doctor_core.py` | 核心分析 — 解析 JSONL、彙整 token | python3（僅標準函式庫） |
| `analyze-visual.py` | 可選圖表產生 | python3 + matplotlib + numpy |
| `doctor`（CLI） | 可選的 DuckDB **倉儲** — 增量 ingest + 可查詢的報告目錄 | uv + duckdb |
| `warehouse.py` / `reports.py` / `reports/` | 倉儲 store/ingest + 報告目錄引擎 | （`doctor` 套件的一部分） |
| `context-doctor.md` | Agent 指令（< 50 行） | 無 |

> **注意：** stdlib JSON 摘要只需要 `python3`（無需 pip 套件）。
> 解析已從逐行 bash/awk 移至 `doctor_core.py`，改從正規的 `.message.usage.*` 路徑讀取 token
> 數值（舊的擷取方式會因 `usage.iterations[]` 而重複計算）。matplotlib/numpy 仍為可選（圖表）；
> `uv`/`duckdb` 也為可選（倉儲）。

---

## 倉儲（可選） {#warehouse-optional}

`doctor` CLI 是一個 DuckDB 後端的**指標倉儲**：不再每次都重新解析所有 JSONL 並只輸出一個固定數值，而是把新 session **增量 ingest** 進本地 store（`~/.claude/context-doctor/metrics.duckdb`），並提供一份**具名、可帶參數的報告目錄** — 分布統計（median/p90）、可設定的 bands、rolling 平均、各 project 彙整 — 全部以 JSON 輸出。

```bash
doctor reports                                              # 列出報告目錄
doctor report summary --days 7                              # 向後相容摘要（與 analyze.sh 同 schema）
doctor report bands --dimension context_tokens --edges 50k,200k,400k
doctor report rolling --metric total_tokens --window 20 --mode days
doctor report <name> --sql                                 # 印出某報告的 SQL（複製/擴充）
doctor ingest                                               # 手動更新（report 會自動先 ingest）
```

可用報告：`summary`、`bands`、`rolling`、`top-expensive`、`by-project`、`cache-health`、`daily`。

**優雅降級。** 倉儲純為附加。`doctor report summary` 輸出與 `analyze.sh` *相同*的 JSON schema，而 `/context-doctor` skill 會優先使用 `doctor`，在缺少 `uv`/`duckdb` 時回退到 stdlib 的 `analyze.sh` — 因此摘要在有無倉儲時都能運作。需要 [`uv`](https://docs.astral.sh/uv)（`uv tool install` 會把 `doctor` 放上 PATH 並一併取得 `duckdb`）。

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

# 倉儲報告（需要 uv + duckdb）
doctor report summary --days 7
doctor report bands --dimension context_tokens --edges 50k,200k,400k
```

---

## 安裝

```bash
# 從本地 clone 安裝 — 安裝 skill + stdlib 腳本，且若有 uv，會透過 `uv tool install`
# 把 `doctor` 倉儲 CLI 放上 PATH（盡力而為；沒有 uv/duckdb 時 stdlib 摘要仍可運作）。
./install.sh context-doctor

# 遠端（僅 skill + stdlib 腳本；倉儲需要本地套件目錄）：
curl -fsSL https://raw.githubusercontent.com/ChrisOr-Dev/claude-commands/main/install.sh | bash -s -- --remote context-doctor

# 或完全手動
mkdir -p ~/.claude/commands/context-doctor
cp context-doctor.md ~/.claude/commands/context-doctor.md
cp analyze.sh doctor_core.py analyze-visual.py ~/.claude/commands/context-doctor/
uv tool install ./context-doctor    # 可選：啟用 `doctor` 倉儲 CLI
```

## 使用

在 Claude Code 中輸入：`/context-doctor`

---

## Credits

- [RyanSeanPhillips](https://github.com/RyanSeanPhillips) — 1M context token burn 分析
- [cldctrl](https://github.com/RyanSeanPhillips/cldctrl) — context_analysis.py
