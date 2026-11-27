import streamlit as st
import os
import pandas as pd
from supabase import create_client, Client

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

# ================= 4. 主工作区：态势地图 (模块二) =================
st.subheader("📍 全球主要热点态势追踪")

# 这里手动维护几个当前的热点坐标，后期你可以改成让 AI 自动提取
hotspots = pd.DataFrame({
    "lat": [50.45, 31.55, 35.69, 25.03, 48.37, 15.55],
    "lon": [30.52, 35.10, 51.39, 121.56, 35.04, 32.53],
    "name": ["Kyiv (俄乌)", "Gaza (中东)", "Tehran (伊朗)", "Taiwan (台海)", "Zaporizhzhia (前线)", "Khartoum (苏丹)"]
})

# 渲染地图，size 控制点的大小，color 设置颜色
st.map(hotspots, latitude="lat", longitude="lon", size=30000, color="#ff4b4b")

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
    
    # 安全展示：直接用 st.markdown
    summary_text = latest.get("summary", "")
    if summary_text:
        st.markdown(summary_text)
    else:
        st.warning("最新记录里没有 summary 字段。")
        
    st.divider()
    st.caption("提示：本页面不再现场抓取和调用 AI，所有内容由后台定时任务生成并写入 Supabase。")
