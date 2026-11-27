import streamlit as st
import os
import pandas as pd
import pydeck as pdk
from supabase import create_client, Client

# ================= 页面基础设置 =================
st.set_page_config(page_title="全球政军情报主编", page_icon="🌍", layout="wide")
st.title("🌍 全球政军情报指挥中心")
st.write("后台每日自动抓取、AI 研判并写入云端；本页面只负责读取和展示最新内参。")

# ================= 1. 安全获取配置 =================
try:
    supabase_url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
except Exception as e:
    st.error(f"读取 Secrets 配置失败: {e}")
    st.stop()

if not supabase_url or not supabase_key:
    st.error("⚠️ 配置缺失：请在 Streamlit Cloud 的 Secrets 中填写 SUPABASE_URL 和 SUPABASE_KEY。")
    st.stop()

# ================= 2. 连接数据库 =================
try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error(f"❌ 数据库连接失败，请检查 URL 和 KEY 是否正确: {e}")
    st.stop()

# ================= 3. 侧边栏：历史记录 =================
with st.sidebar:
    st.header("☁️ 云端历史情报库")
    try:
        # 获取所有历史数据
        response = supabase.table("history").select("*").order("time", desc=True).execute()
        history_data = response.data or []
    except Exception as e:
        st.error(f"读取云端失败: {e}")
        history_data = []

    if not history_data:
        st.info("云端暂无记录，等后台定时任务跑完后再来看。")
    else:
        for item in history_data:
            with st.expander(f"🕒 {item.get('time', '未知时间')}"):
                st.markdown(item.get("summary", "无内容"))
                if st.button("🗑️ 删除此条", key=f"del_{item.get('id')}"):
                    try:
                        supabase.table("history").delete().eq("id", item.get("id")).execute()
                        st.rerun()
                    except Exception as e:
                        st.error(f"删除失败：{e}")

# ================= 4. 主工作区：态势地图 =================
st.subheader("📍 全球主要热点态势追踪")

# 构建带有中文名称的数据
hotspot_data = pd.DataFrame({
    "name": ["基辅 (俄乌)", "加沙 (中东)", "德黑兰 (伊朗)", "台海 (印太)", "哈尔科夫 (前线)", "喀土穆 (苏丹)"],
    "lat": [50.45, 31.55, 35.69, 25.03, 49.99, 15.55],
    "lon": [30.52, 35.10, 51.39, 121.56, 36.23, 32.53]
})

# 1. 定义红点图层 (稍微调大点)
scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    hotspot_data,
    get_position=["lon", "lat"],
    get_color="[255, 75, 75, 200]", # 红色
    get_radius=50000, 
    pickable=True,
    auto_highlight=True,
)

# 2. 定义中文文字图层（修复了引号错误）
text_layer = pdk.Layer(
    "TextLayer",
    hotspot_data,
    get_position=["lon", "lat"],
    get_text="name",
    get_size=14,
    get_color="[255, 255, 255]", # 白色文字
    get_alignment_baseline="bottom", 
)

# 3. 修复地图重复问题：中心点往左移，稍微放大
view_state = pdk.ViewState(
    latitude=30, 
    longitude=20,  # 从 50 改到 20，避免地图拼接
    zoom=1.5,      # 放大一点，让地图占满屏幕
    pitch=0
)

# 4. 渲染地图
st.pydeck_chart(
    pdk.Deck(
        layers=[scatter_layer, text_layer],
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={"text": "{name}"} 
    )
)

st.divider()

# ================= 5. 主工作区：最新内参 =================
if st.button("🔄 刷新最新情报", type="primary", use_container_width=True):
    st.rerun()

if not history_data:
    st.warning("还没有数据。请确认 GitHub Actions 已经成功运行并写入了 Supabase。")
else:
    latest = history_data[0]
    
    st.subheader(f"📌 最新内参：{latest.get('topic', '全球军政内参')}")
    st.caption(f"更新时间：{latest.get('time', '未知时间')}")
    
    summary_text = latest.get("summary", "")
    if summary_text:
        st.markdown(summary_text)
    else:
        st.warning("最新记录里没有 summary 字段。")
        
    st.divider()
    st.caption("提示：本页面不再现场抓取和调用 AI，所有内容由后台定时任务生成并写入 Supabase。")
