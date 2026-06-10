"""
YouBike 2.0 資料採集服務
負責向政府開放資料平台抓取即時站點資訊，並附加時間戳記儲存至 CSV。
"""

import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# ── 設定日誌 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 常數設定 ──────────────────────────────────────────────────────────────────
# 台北市 YouBike 2.0 開放資料 API
TAIPEI_API_URL = (
    "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
)

# 新北市 YouBike 2.0 開放資料 API
NEW_TAIPEI_API_URL = (
    "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4176-a47b-c221f4299e2e"
    "/json?page=0&size=1000"
)

# 各縣市 API 設定
CITY_APIS: dict[str, str] = {
    "taipei": TAIPEI_API_URL,
    "new_taipei": NEW_TAIPEI_API_URL,
}

# 欲擷取並保留的欄位（對應 API 回傳的欄位名稱）
TAIPEI_FIELD_MAP: dict[str, str] = {
    "sno": "station_id",                    # 站點編號
    "sna": "station_name",                  # 站點名稱（中文）
    "snaen": "station_name_en",             # 站點名稱（英文）
    "Quantity": "total_docks",              # 總車柱數
    "available_rent_bikes": "available_bikes",   # 目前可借車輛數
    "available_return_bikes": "empty_docks",     # 目前可還空柱數
    "latitude": "latitude",                 # 緯度
    "longitude": "longitude",               # 經度
    "ar": "address",                        # 地址（中文）
    "sarea": "district",                    # 行政區
    "infoTime": "data_updated_at",          # 資料來源更新時間
}

# 資料儲存路徑
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# 採集間隔（秒）
FETCH_INTERVAL_SECONDS = 300  # 5 分鐘


# ── 資料抓取 ──────────────────────────────────────────────────────────────────

def fetch_taipei_youbike() -> list[dict] | None:
    """
    向台北市開放資料平台發送請求，取得 YouBike 2.0 即時資訊。
    回傳原始 JSON 列表，失敗時回傳 None。
    """
    logger.info("開始抓取台北市 YouBike 2.0 即時資料...")
    try:
        response = requests.get(TAIPEI_API_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
        logger.info(f"成功取得 {len(data)} 筆站點資料")
        return data
    except requests.exceptions.Timeout:
        logger.error("API 請求逾時（超過 15 秒），略過本次採集")
    except requests.exceptions.ConnectionError:
        logger.error("網路連線失敗，略過本次採集")
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP 錯誤：{e}，略過本次採集")
    except Exception as e:
        logger.error(f"未預期的錯誤：{e}，略過本次採集")
    return None


# ── 資料清洗 ──────────────────────────────────────────────────────────────────

def parse_taipei_data(raw_data: list[dict], timestamp: datetime) -> pd.DataFrame:
    """
    將台北市 API 原始 JSON 轉換為結構化 DataFrame。
    - 重新命名欄位為易讀的英文名稱
    - 附加採集時間戳記
    - 轉換數值型別
    """
    df = pd.DataFrame(raw_data)

    # 只保留需要的欄位（忽略 API 中多餘的欄位）
    existing_fields = {k: v for k, v in TAIPEI_FIELD_MAP.items() if k in df.columns}
    df = df[list(existing_fields.keys())].rename(columns=existing_fields)

    # 附加時間戳記
    df["fetched_at"] = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    # 轉換數值型別，非數值填入 0（API 偶爾回傳空字串）
    for col in ["total_docks", "available_bikes", "empty_docks"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # 轉換座標型別
    for col in ["latitude", "longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"資料解析完成，共 {len(df)} 筆、{len(df.columns)} 個欄位")
    return df


# ── 資料儲存 ──────────────────────────────────────────────────────────────────

def save_to_csv(df: pd.DataFrame, city: str = "taipei") -> Path:
    """
    以 Append 模式將 DataFrame 寫入 CSV，每天產生一個獨立檔案。
    若當天檔案不存在則建立新檔並寫入表頭；若已存在則附加資料（不重複表頭）。
    回傳寫入的檔案路徑。
    """
    today = datetime.now().strftime("%Y%m%d")
    csv_path = DATA_DIR / f"youbike_{city}_{today}.csv"

    file_exists = csv_path.exists()
    df.to_csv(csv_path, mode="a", header=not file_exists, index=False, encoding="utf-8-sig")

    action = "附加至" if file_exists else "建立並寫入"
    logger.info(f"資料已{action}：{csv_path}（新增 {len(df)} 筆）")
    return csv_path


# ── 單次採集流程 ──────────────────────────────────────────────────────────────

def _get_next_run_time() -> str:
    """
    以 GitHub Actions cron '*/5 * * * *'（UTC）為基準，
    計算下一個 UTC 5 分鐘整點並轉換為本地時間回傳。
    """
    from datetime import timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    next_minute = (now_utc.minute // 5 + 1) * 5
    if next_minute >= 60:
        next_utc = now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_utc = now_utc.replace(minute=next_minute, second=0, microsecond=0)
    return next_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def export_latest_json(df: pd.DataFrame) -> None:
    """
    將最新快照與歷史趨勢摘要匯出為 data/latest.json，供 index.html 讀取。
    每次採集後呼叫，覆蓋上一次的結果。
    趨勢採累積模式：讀取現有 latest.json 的 trend，附加本次快照，保留最近 24 小時（288 筆）。
    """
    import glob, json

    TREND_MAX = 288  # 5 分鐘間隔 × 288 = 24 小時

    # 本次採集的全市統計快照
    new_snapshot = {
        "fetched_at": df["fetched_at"].iloc[0] if len(df) else "",
        "available_bikes": int(df["available_bikes"].sum()),
        "empty_docks": int(df["empty_docks"].sum()),
        "station_count": int(df["station_id"].nunique()),
    }

    # 讀取現有 latest.json 中的歷史趨勢（跨次執行累積）
    existing_trend: list[dict] = []
    json_path = DATA_DIR / "latest.json"
    if json_path.exists():
        try:
            existing = json.loads(json_path.read_text(encoding="utf-8"))
            existing_trend = existing.get("trend", [])
        except Exception:
            existing_trend = []

    # 若 JSON 趨勢為空且本地有 CSV，從 CSV 補齊初始歷史
    if not existing_trend:
        all_files = sorted(glob.glob(str(DATA_DIR / "youbike_taipei_*.csv")))
        if all_files:
            hist = pd.concat(
                [pd.read_csv(f, encoding="utf-8-sig") for f in all_files],
                ignore_index=True,
            )
            trend_df = (
                hist.groupby("fetched_at")
                .agg(
                    available_bikes=("available_bikes", "sum"),
                    empty_docks=("empty_docks", "sum"),
                    station_count=("station_id", "nunique"),
                )
                .reset_index()
                .sort_values("fetched_at")
            )
            existing_trend = trend_df.to_dict(orient="records")

    # 合併：避免重複時間戳，附加本次快照，只保留最新 TREND_MAX 筆
    existing_times = {r["fetched_at"] for r in existing_trend}
    if new_snapshot["fetched_at"] and new_snapshot["fetched_at"] not in existing_times:
        existing_trend.append(new_snapshot)
    trend_records = sorted(existing_trend, key=lambda r: r["fetched_at"])[-TREND_MAX:]

    # 行政區統計（最新快照）
    district = (
        df.groupby("district")["available_bikes"]
        .mean()
        .round(1)
        .reset_index()
        .sort_values("available_bikes", ascending=False)
        .to_dict(orient="records")
    )

    # 可借車輛不足警示（最新快照）
    warning = (
        df[df["available_bikes"] < 3]
        [["station_name", "district", "available_bikes", "empty_docks", "total_docks"]]
        .sort_values("available_bikes")
        .to_dict(orient="records")
    )

    # 可借車輛分布區間（最新快照）
    bins   = [0, 1, 5, 10, 20, float("inf")]
    labels = ["0台（無車）", "1-4台", "5-9台", "10-19台", "20台以上"]
    df_copy = df.copy()
    df_copy["bucket"] = pd.cut(df_copy["available_bikes"], bins=bins, labels=labels, right=False)
    dist = df_copy["bucket"].value_counts().reindex(labels).fillna(0).astype(int)
    dist_records = [{"label": k, "count": int(v)} for k, v in dist.items()]

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latest_fetched_at": df["fetched_at"].iloc[0] if len(df) else "",
        "next_run_time": _get_next_run_time(),
        "total_snapshots": len(trend_records),
        "total_stations": int(df["station_id"].nunique()),
        "total_available_bikes": int(df["available_bikes"].sum()),
        "total_empty_docks": int(df["empty_docks"].sum()),
        "trend": trend_records,
        "district": district,
        "distribution": dist_records,
        "warnings": warning,
    }

    # 同時輸出 latest.json（供 Streamlit dashboard）與 data.js（供 index.html 直接開啟）
    json_path = DATA_DIR / "latest.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"latest.json 已更新：{json_path}")

    # data.js 用 window.ECOBIKE_DATA 變數注入，<script src> 在 file:// 下可正常讀取
    js_path = DATA_DIR / "data.js"
    js_content = "window.ECOBIKE_DATA = " + json.dumps(payload, ensure_ascii=False) + ";"
    js_path.write_text(js_content, encoding="utf-8")
    logger.info(f"data.js 已更新：{js_path}")


def collect_once() -> bool:
    """
    執行一次完整的採集流程：抓取 → 解析 → 儲存 → 匯出 JSON。
    成功回傳 True，失敗回傳 False。
    """
    timestamp = datetime.now()
    logger.info(f"===== 採集任務開始：{timestamp.strftime('%Y-%m-%d %H:%M:%S')} =====")

    raw_data = fetch_taipei_youbike()
    if raw_data is None:
        logger.warning("本次採集失敗，資料未寫入")
        return False

    df = parse_taipei_data(raw_data, timestamp)
    csv_path = save_to_csv(df, city="taipei")
    export_latest_json(df)

    logger.info(f"===== 採集任務完成，資料儲存於：{csv_path} =====\n")
    return True


# ── 背景排程服務 ──────────────────────────────────────────────────────────────

def run_scheduler(interval_seconds: int = FETCH_INTERVAL_SECONDS) -> None:
    """
    持續執行背景採集迴圈。
    立即執行一次後，每隔 interval_seconds 秒重複採集。
    可用 Ctrl+C 中斷。
    """
    logger.info(f"背景採集服務啟動，採集間隔：{interval_seconds // 60} 分鐘")
    logger.info("按下 Ctrl+C 可停止服務\n")

    while True:
        collect_once()
        logger.info(f"下次採集將於 {interval_seconds // 60} 分鐘後執行...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    # 直接執行此檔案時啟動排程服務
    run_scheduler()
