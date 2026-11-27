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
    st.header("☁️ 历史情报库")
    try:
        response = supabase.table("history").select("*").order("time", desc=True).execute()
        history_data = response.data or []
    except Exception as e:
        st.error(f"读取云端失败: {e}")
        history_data = []

    if not history_data:
        st.info("暂无历史记录。")
    else:
        for item in history_data:
            with st.expander(f"🕒 {item.get('time', '未知时间')}"):
                # 为了侧边栏不至于太长，只显示前几百个字符
                preview_text = item.get("summary", "")[:300] + "..."
                st.markdown(preview_text)
                if st.button("🗑️ 删除", key=f"del_{item.get('id')}"):
                    supabase.table("history").delete().eq("id", item.get("id")).execute()
                    st.rerun()

# ================= 3. 数据看板 =================
if history_data:
    latest = history_data[0]
    total_records = len(history_data)
    latest_time = latest.get('time', '未知')
    
    col1, col2, col3 = st.columns(3)
    col1.metric("云端情报总数", f"{total_records} 份")
    col2.metric("最新研判时间", latest_time)
    col3.metric("系统状态", "🟢 实时更新中")
    st.divider()

# ================= 4. 深色战术地图 =================
st.subheader("📍 全球热点态势分布")

hotspot_data = pd.DataFrame({
    "name": ["基辅 (俄乌)", "加沙 (中东)", "德黑兰 (伊朗)", "台海 (印太)", "哈尔科夫 (前线)", "喀土穆 (苏丹)"],
    "lat": [50.45, 31.55, 35.69, 25.03, 49.99, 15.55],
    "lon": [30.52, 35.10, 51.39, 121.56, 36.23, 32.53]
})

layer = pdk.Layer(
    "ScatterplotLayer",
    hotspot_data,
    get_position=["lon", "lat"],
    get_color=[255, 50, 50, 220],
    get_radius=80000,
    pickable=True,
)
view_state = pdk.ViewState(latitude=25, longitude=60, zoom=1.5, pitch=0)

st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={"text": "📍 {name}"}
    )
)
st.caption("🔴 热点区域：东欧 | 中东 | 台海 | 非洲")

st.divider()

# ================= 5. 详细内参展示区 =================
if st.button("🔄 刷新最新情报", type="primary", use_container_width=True):
    st.rerun()

if not history_data:
    st.warning("还没有数据。请确认 GitHub Actions 已经成功运行并写入了 Supabase。")
else:
    # 用卡片包裹，增加阅读感
    with st.container(border=True):
        st.subheader(f"📌 最新深度内参：{latest.get('topic', '全球军政内参')}")
        st.caption(f"生成时间：{latest.get('time')}")
        st.divider()
        
        summary_text = latest.get("summary", "")
        if summary_text:
            # 直接渲染详细的 Markdown
            st.markdown(summary_text)
        else:
            st.warning("最新记录里没有 summary 字段。")
        
    st.caption("提示：本页面不再现场抓取和调用 AI，所有内容由后台定时任务生成并写入 Supabase。")
