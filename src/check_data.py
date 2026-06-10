"""
快速檢查採集到的 CSV 資料內容，供開發與除錯使用。
"""

from pathlib import Path
import pandas as pd
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"


def check_latest() -> None:
    csv_files = sorted(DATA_DIR.glob("youbike_taipei_*.csv"), reverse=True)
    if not csv_files:
        print("尚無資料，請先執行 collector.py")
        return

    latest = csv_files[0]
    df = pd.read_csv(latest, encoding="utf-8-sig")

    print(f"\n[資料檔案] 最新資料檔案：{latest.name}")
    print(f"[統計] 總筆數：{len(df)} 筆")
    print(f"[時間] 採集時間點數量：{df['fetched_at'].nunique()} 個時間點")
    print(f"\n欄位一覽：\n{df.dtypes}")
    print(f"\n前 5 筆資料預覽：\n{df.head()}")
    print(f"\n可用車輛統計：\n{df['available_bikes'].describe()}")


if __name__ == "__main__":
    check_latest()
