"""
EcoBike Insight — 即時採集狀況儀表板
每 60 秒自動刷新，顯示採集進度、站點統計與供需趨勢。
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── 頁面設定 ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="EcoBike Insight — 採集狀況",
    page_icon="🚲",
    layout="wide",
)

DATA_DIR = Path(__file__).parent.parent / "data"
REFRESH_SECONDS = 60


# ── 資料載入 ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=REFRESH_SECONDS)
def load_all_data() -> pd.DataFrame:
    """載入所有 CSV 並合併，快取 60 秒。"""
    files = sorted(DATA_DIR.glob("youbike_taipei_*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat(
        [pd.read_csv(f, encoding="utf-8-sig") for f in files],
        ignore_index=True,
    )
    df["fetched_at"] = pd.to_datetime(df["fetched_at"])
    return df


# ── 主畫面 ────────────────────────────────────────────────────────────────────

st.title("🚲 EcoBike Insight — 資料採集即時狀況")
st.caption(f"每 {REFRESH_SECONDS} 秒自動刷新 | 資料來源：台北市政府開放資料平台")

df = load_all_data()

if df.empty:
    st.warning("尚無採集資料，請先啟動 collector.py 或等待排程執行。")
    st.stop()

# ── 基本指標 ──────────────────────────────────────────────────────────────────
snapshots = sorted(df["fetched_at"].unique())
latest_time = snapshots[-1]
first_time = snapshots[0]
snapshot_count = len(snapshots)
latest_df = df[df["fetched_at"] == latest_time]

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("最新採集時間", latest_time.strftime("%H:%M:%S"))
col2.metric("累積採集次數", f"{snapshot_count} 次")
col3.metric("監控站點數", f"{latest_df['station_id'].nunique()} 站")
col4.metric("全市可借車輛", f"{int(latest_df['available_bikes'].sum())} 台")
col5.metric("全市可還空柱", f"{int(latest_df['empty_docks'].sum())} 格")

st.divider()

# ── 採集紀錄時間軸 ────────────────────────────────────────────────────────────
st.subheader("採集紀錄")

timeline_df = (
    df.groupby("fetched_at")
    .agg(
        站點數=("station_id", "nunique"),
        總可借車輛=("available_bikes", "sum"),
        總可還空柱=("empty_docks", "sum"),
    )
    .reset_index()
    .rename(columns={"fetched_at": "採集時間"})
)
timeline_df["採集時間"] = timeline_df["採集時間"].dt.strftime("%Y-%m-%d %H:%M:%S")
st.dataframe(timeline_df, use_container_width=True, hide_index=True)

st.divider()

# ── 全市可借車輛趨勢 ──────────────────────────────────────────────────────────
st.subheader("全市可借車輛數趨勢")

trend_df = (
    df.groupby("fetched_at")
    .agg(可借車輛=("available_bikes", "sum"), 可還空柱=("empty_docks", "sum"))
    .reset_index()
)

fig_trend = go.Figure()
fig_trend.add_trace(go.Scatter(
    x=trend_df["fetched_at"], y=trend_df["可借車輛"],
    name="可借車輛", mode="lines+markers",
    line=dict(color="#2ecc71", width=2),
    marker=dict(size=8),
))
fig_trend.add_trace(go.Scatter(
    x=trend_df["fetched_at"], y=trend_df["可還空柱"],
    name="可還空柱", mode="lines+markers",
    line=dict(color="#3498db", width=2),
    marker=dict(size=8),
))
fig_trend.update_layout(
    xaxis_title="採集時間",
    yaxis_title="數量（台 / 格）",
    legend=dict(orientation="h", y=1.1),
    hovermode="x unified",
    height=350,
)
st.plotly_chart(fig_trend, use_container_width=True)

st.divider()

# ── 最新快照：可借車輛分布 ────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("可借車輛分布（最新快照）")
    bins = [0, 1, 5, 10, 20, float("inf")]
    labels = ["0台（無車）", "1-4台", "5-9台", "10-19台", "20台以上"]
    latest_df = latest_df.copy()
    latest_df["區間"] = pd.cut(latest_df["available_bikes"], bins=bins, labels=labels, right=False)
    dist_df = latest_df["區間"].value_counts().reindex(labels).reset_index()
    dist_df.columns = ["可借車輛區間", "站點數"]
    colors = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#27ae60"]
    fig_dist = px.bar(dist_df, x="可借車輛區間", y="站點數", color="可借車輛區間",
                      color_discrete_sequence=colors, height=320)
    fig_dist.update_layout(showlegend=False, xaxis_title="", yaxis_title="站點數")
    st.plotly_chart(fig_dist, use_container_width=True)

with col_right:
    st.subheader("各行政區平均可借車輛（最新快照）")
    if "district" in latest_df.columns:
        district_df = (
            latest_df.groupby("district")["available_bikes"]
            .mean()
            .round(1)
            .reset_index()
            .sort_values("available_bikes", ascending=True)
        )
        district_df.columns = ["行政區", "平均可借車輛"]
        # 清除站名前綴（例如「大安區」）
        fig_dist2 = px.bar(
            district_df, x="平均可借車輛", y="行政區",
            orientation="h", height=320,
            color="平均可借車輛", color_continuous_scale="Greens",
        )
        fig_dist2.update_layout(coloraxis_showscale=False, yaxis_title="")
        st.plotly_chart(fig_dist2, use_container_width=True)
    else:
        st.info("缺少行政區欄位")

st.divider()

# ── 可借車輛最少的站點（預警） ─────────────────────────────────────────────────
st.subheader("可借車輛不足警示（最新快照，可借 < 3 台）")
warning_df = (
    latest_df[latest_df["available_bikes"] < 3]
    [["station_name", "district", "available_bikes", "empty_docks", "total_docks"]]
    .sort_values("available_bikes")
    .rename(columns={
        "station_name": "站點名稱",
        "district": "行政區",
        "available_bikes": "可借車輛",
        "empty_docks": "可還空柱",
        "total_docks": "總車柱",
    })
)
if warning_df.empty:
    st.success("目前無可借車輛不足的站點")
else:
    st.warning(f"共 {len(warning_df)} 個站點可借車輛不足 3 台")
    st.dataframe(warning_df, use_container_width=True, hide_index=True)

# ── 自動刷新 ──────────────────────────────────────────────────────────────────
st.caption(f"頁面將於 {REFRESH_SECONDS} 秒後自動刷新 | 最後更新：{datetime.now().strftime('%H:%M:%S')}")
st.markdown(
    f"""<meta http-equiv="refresh" content="{REFRESH_SECONDS}">""",
    unsafe_allow_html=True,
)
