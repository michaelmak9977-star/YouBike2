# EcoBike Insight — 專案說明

## 專案目的

將台北市 YouBike 2.0 開放資料轉化為「供需預報系統」，協助通勤族掌握站點即時車輛動態。
完整規格書見 [YouBike2.md](YouBike2.md)。

---

## 技術棧

- **語言**：Python 3.12，使用 `uv` 管理套件
- **後端套件**：`requests`、`pandas`、`schedule`
- **前端**：純 HTML + Chart.js（`index.html`），無需伺服器即可開啟
- **視覺化儀表板（可選）**：Streamlit + Plotly（`src/dashboard.py`）

---

## 專案結構

```
YouBike2/
├── src/
│   ├── collector.py        # 核心採集模組（抓取 API、清洗、儲存 CSV、匯出 data.js）
│   ├── collector_once.py   # 單次採集入口，供 Windows 工作排程器呼叫
│   ├── check_data.py       # 快速檢查 CSV 資料內容（開發用）
│   └── dashboard.py        # Streamlit 即時儀表板（可選）
├── data/                   # 採集資料（不納入 Git）
│   ├── youbike_taipei_YYYYMMDD.csv   # 每日累積 CSV
│   ├── latest.json         # 最新快照 JSON（供 Streamlit 使用）
│   └── data.js             # 最新快照 JS（供 index.html file:// 直接開啟）
├── index.html              # 靜態儀表板，雙擊即可開啟
├── CLAUDE.md               # 本文件
├── YouBike2.md             # APP 企劃規格書
├── pyproject.toml          # uv 專案設定
└── uv.lock                 # 套件鎖定版本
```

---

## 資料來源

| 縣市 | API URL |
|------|---------|
| 台北市 | `https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json` |

### 實際 API 欄位對應（v2 與舊版不同，勿混淆）

| API 欄位 | 內部欄位名 | 說明 |
|---|---|---|
| `sno` | `station_id` | 站點編號 |
| `sna` | `station_name` | 站點名稱（中文） |
| `Quantity` | `total_docks` | 總車柱數 |
| `available_rent_bikes` | `available_bikes` | 可借車輛數 |
| `available_return_bikes` | `empty_docks` | 可還空柱數 |
| `sarea` | `district` | 行政區 |

---

## 核心流程

```
Windows 工作排程器（每 2 分鐘）
  → src/collector_once.py
  → collector.py: fetch API → 清洗 → 附加時間戳記
  → 寫入 data/youbike_taipei_YYYYMMDD.csv（Append 模式）
  → 匯出 data/latest.json（供 Streamlit）
  → 匯出 data/data.js（供 index.html，window.ECOBIKE_DATA）
```

---

## 啟動方式

### 在新電腦上初始化

```powershell
cd "C:\Users\<使用者名稱>\Documents\YouBike2"
uv sync
```

### 設定 Windows 工作排程器（每 2 分鐘自動採集）

```powershell
$user      = $env:USERNAME
$base      = "C:\Users\$user\Documents\YouBike2"
$pythonExe = "$base\.venv\Scripts\python.exe"
$scriptPath = "$base\src\collector_once.py"
$taskName  = "YouBike2_DataCollector"

$trigger  = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 2) -Once -At (Get-Date)
$action   = New-ScheduledTaskAction -Execute $pythonExe -Argument $scriptPath -WorkingDirectory $base
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew -StartWhenAvailable -RunOnlyIfNetworkAvailable

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action -Settings $settings `
    -Description "每 2 分鐘自動抓取台北市 YouBike 2.0 即時資料" -RunLevel Limited -Force

Start-ScheduledTask -TaskName $taskName
```

### 開啟靜態儀表板

直接雙擊 `index.html`（需先有 `data/data.js`，排程器執行一次後自動產生）。

### 開啟 Streamlit 儀表板（可選）

```powershell
uv run streamlit run src/dashboard.py
# 瀏覽器開啟 http://localhost:8501
```

### 手動觸發單次採集（測試用）

```powershell
uv run python src/collector_once.py
```

---

## 重要設計決策

### index.html 使用 data.js 而非 fetch()
瀏覽器以 `file://` 開啟 HTML 時，`fetch()` 會被 CORS 封鎖。
解法：採集器每次執行後同時寫出 `data/data.js`，內容為 `window.ECOBIKE_DATA = {...}`，
`index.html` 用 `<script src>` 載入，完全不依賴伺服器。

### 頁面刷新對齊採集時間
頁面倒數計時不使用固定秒數，而是讀取 `data.js` 中的 `next_run_time`，
計算距離下次採集還有多少秒，再加 10 秒緩衝後刷新，確保頁面永遠顯示最新採集結果。

### CSV 每日一檔 + Append 模式
每天產生獨立的 `youbike_taipei_YYYYMMDD.csv`，以 Append 方式累積，
不覆蓋歷史資料，保留完整時間序列供後續分析。

---

## 待實作功能（規格書 Next Steps）

- [ ] 「我的最愛」站點篩選（第二階段）
- [ ] 天氣 API 整合，對比晴雨天租借率差異
- [ ] 推播通知：常用站點可借車輛低於 3 台時通知
- [ ] 機器學習：預測未來 30 分鐘車位狀況
