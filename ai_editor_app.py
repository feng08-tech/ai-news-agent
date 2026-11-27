import streamlit as st
import os
import pandas as pd
import pydeck as pdk
from supabase import create_client, Client

st.set_page_config(page_title="全球政军情报主编", page_icon="🌍", layout="wide")
st.title("🌍 全球政军情报指挥中心")
st.write("后台每日自动抓取、AI 研判并写入云端；本页面只负责读取和展示最新内参。")

# ================= 1. 配置与连接 =================
try:
    supabase_url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
except Exception as e:
    st.error(f"读取 Secrets 配置失败: {e}")
    st.stop()

if not supabase_url or not supabase_key:
    st.error("⚠️ 配置缺失：请在 Streamlit Cloud 的 Secrets 中填写。")
    st.stop()

try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error(f"❌ 数据库连接失败: {e}")
    st.stop()

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.header("☁️ 云端历史情报库")
    try:
        response = supabase.table("history").select("*").order("time", desc=True).execute()
        history_data = response.data or []
    except Exception as e:
        st.error(f"读取云端失败: {e}")
        history_data = []

    if not history_data:
        st.info("云端暂无记录。")
    else:
        for item in history_data:
            with st.expander(f"🕒 {item.get('time', '未知时间')}"):
                st.markdown(item.get("summary", "无内容"))
                if st.button("🗑️ 删除此条", key=f"del_{item.get('id')}"):
                    supabase.table("history").delete().eq("id", item.get("id")).execute()
                    st.rerun()

# ================= 3. 态势地图 =================
st.subheader("📍 全球主要热点态势追踪 (鼠标悬停查看中文地名)")

hotspot_data = pd.DataFrame({
    "name": ["基辅 (俄乌)", "加沙 (中东)", "德黑兰 (伊朗)", "台海 (印太)", "哈尔科夫 (前线)", "喀土穆 (苏丹)"],
    "lat": [50.45, 31.55, 35.69, 25.03, 49.99, 15.55],
    "lon": [30.52, 35.10, 51.39, 121.56, 36.23, 32.53]
})

# 极简图层，只留红点
layer = pdk.Layer(
    "ScatterplotLayer",
    hotspot_data,
    get_position=["lon", "lat"],
    get_color=[255, 50, 50, 200], # 纯红
    get_radius=150000, # 半径调大，防止看不见
    pickable=True,
)

# 视角调整：放在大西洋中间，避免三连屏
view_state = pdk.ViewState(
    latitude=20,
    longitude=0, 
    zoom=0.8, # 稍微拉远一点看全景
    pitch=0
)

# 渲染
st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={"text": "📍 {name}"} # 鼠标悬浮显示中文
    )
)

st.divider()

# ================= 4. 最新内参 =================
if st.button("🔄 刷新最新情报", type="primary", use_container_width=True):
    st.rerun()

if history_data:
    latest = history_data[0]
    st.subheader(f"📌 最新内参：{latest.get('topic', '全球军政内参')}")
    st.caption(f"更新时间：{latest.get('time', '未知时间')}")
    st.markdown(latest.get("summary", "无内容"))
