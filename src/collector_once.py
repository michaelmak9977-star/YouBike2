"""
單次採集入口點，供 Windows 工作排程器呼叫。
每次排程觸發時執行一次採集，不進入迴圈。
"""

import sys
from pathlib import Path

# 確保可以 import 同層模組
sys.path.insert(0, str(Path(__file__).parent))

from collector import collect_once

if __name__ == "__main__":
    success = collect_once()
    sys.exit(0 if success else 1)
