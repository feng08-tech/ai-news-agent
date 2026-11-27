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

# ================= 3. 左右分栏：地图与最新内参 =================
# 将页面分成左右 6:4 的比例
col_map, col_text = st.columns([6, 4])

with col_map:
    st.subheader("📍 全球主要热点态势")
    
    hotspot_data = pd.DataFrame({
        "name": ["基辅", "加沙", "德黑兰", "台海", "哈尔科夫", "喀土穆"],
        "lat": [50.45, 31.55, 35.69, 25.03, 49.99, 15.55],
        "lon": [30.52, 35.10, 51.39, 121.56, 36.23, 32.53]
    })

    # 1. 红点图层
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        hotspot_data,
        get_position=["lon", "lat"],
        get_color="[255, 50, 50, 200]", 
        get_radius=80000, # 点调大一点
        pickable=True,
    )

    # 2. 中文文字图层（这次指定了字体和位置偏移，防止重叠）
    text_layer = pdk.Layer(
        "TextLayer",
        hotspot_data,
        get_position=["lon", "lat"],
        get_text="name",
        get_size=16,
        get_color="[255, 255, 255]", # 白色
        get_alignment_baseline="'bottom'",
    )

    # 视角：中心点定在东半球（经度 80），放大到 1.2，这样就不会出现三连屏了
    view_state = pdk.ViewState(
        latitude=30, 
        longitude=80, 
        zoom=1.2, 
        pitch=0
    )

    st.pydeck_chart(
        pdk.Deck(
            layers=[scatter_layer, text_layer],
            initial_view_state=view_state,
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            tooltip={"text": "{name}"} 
        )
    )

with col_text:
    st.subheader("📌 最新内参")
    if st.button("🔄 刷新最新情报", type="primary", use_container_width=True):
        st.rerun()

    if history_data:
        latest = history_data[0]
        st.caption(f"更新时间：{latest.get('time', '未知时间')}")
        st.markdown(latest.get("summary", "无内容"))
    else:
        st.warning("还没有数据。")

st.divider()
st.caption("提示：本页面所有内容由后台定时任务生成并写入 Supabase。")
