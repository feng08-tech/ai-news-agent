import streamlit as st
import os
import pandas as pd
import pydeck as pdk
from supabase import create_client, Client
from openai import OpenAI

st.set_page_config(page_title="全球政军情报主编", page_icon="🌍", layout="wide")
st.title("🌍 全球政军情报指挥中心")
st.write("后台每日自动抓取、AI 研判并写入云端；本页面支持读取、展示、手动搜索与即时分析。")

# ================= 1. 配置与连接 =================
try:
    supabase_url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
    deepseek_key = st.secrets.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
except Exception as e:
    st.error(f"读取 Secrets 配置失败: {e}")
    st.stop()

if not supabase_url or not supabase_key:
    st.error("⚠️ 配置缺失：请在 Streamlit Cloud 的 Secrets 中填写 SUPABASE_URL 和 SUPABASE_KEY。")
    st.stop()

try:
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    st.error(f"❌ 数据库连接失败: {e}")
    st.stop()


def analyze_text(text: str, focus: str = "提炼要点、判断影响、给出后续观察指标") -> str:
    """调用 DeepSeek 对给定文本做分析。"""
    if not deepseek_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 Secrets 中添加。")
    client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一名严谨的军政情报分析助手，只基于给定材料分析，不编造。"},
            {"role": "user", "content": f"请基于以下内容进行分析。重点：{focus}\n\n{text}"}
        ],
        temperature=0.3
    )
    return resp.choices[0].message.content


# ================= 2. 侧边栏 =================
with st.sidebar:
    st.header("🔍 手动搜索")
    keyword = st.text_input("输入关键词", placeholder="例如：台海、俄乌、无人机")
    search_limit = st.slider("最多显示条数", 5, 50, 20)
    st.divider()

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
                preview_text = (item.get("summary") or "")[:300] + "..."
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

# ================= 5. 详细内参 / 搜索结果展示区 =================
if st.button("🔄 刷新最新情报", type="primary", use_container_width=True):
    st.rerun()

if keyword:
    # ---------- 搜索模式 ----------
    kw = keyword.strip().lower()
    matched = [
        item for item in history_data
        if kw in (item.get("topic") or "").lower()
        or kw in (item.get("summary") or "").lower()
    ][:search_limit]

    st.subheader(f"🔍 搜索结果：{keyword}（{len(matched)} 条）")

    if not matched:
        st.info("没有找到匹配内容，换个关键词试试。")
    else:
        # 主题简报
        if st.button("📝 生成主题简报", use_container_width=True):
            material = "\n\n".join([
                f"主题：{item.get('topic', '')}\n时间：{item.get('time', '')}\n内容：{(item.get('summary') or '')[:800]}"
                for item in matched[:10]
            ])
            with st.spinner("正在生成主题简报..."):
                try:
                    st.session_state["search_brief"] = analyze_text(
                        material,
                        focus="汇总相关动态、判断趋势、列出关键风险点和后续观察指标"
                    )
                    st.session_state["search_brief_keyword"] = keyword
                except Exception as e:
                    st.error(f"简报生成失败：{e}")

        if st.session_state.get("search_brief") and st.session_state.get("search_brief_keyword") == keyword:
            with st.container(border=True):
                st.markdown("### 📝 主题简报")
                st.markdown(st.session_state["search_brief"])

        st.divider()

        # 逐条结果
        for item in matched:
            item_id = item.get("id")
            summary = item.get("summary") or ""
            with st.container(border=True):
                st.subheader(f"📌 {item.get('topic', '无标题')}")
                st.caption(f"时间：{item.get('time', '未知')}")
                preview = summary[:1200] + ("..." if len(summary) > 1200 else "")
                st.markdown(preview)

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("🤖 AI 分析这条", key=f"ai_{item_id}"):
                        with st.spinner("分析中..."):
                            try:
                                st.session_state[f"analysis_{item_id}"] = analyze_text(summary)
                            except Exception as e:
                                st.error(f"分析失败：{e}")
                with col_b:
                    if st.button("📖 查看全文", key=f"full_{item_id}"):
                        st.session_state[f"full_{item_id}"] = True

                if st.session_state.get(f"full_{item_id}"):
                    st.markdown("#### 📖 全文")
                    st.markdown(summary)
                if st.session_state.get(f"analysis_{item_id}"):
                    st.markdown("#### 🤖 AI 分析")
                    st.markdown(st.session_state[f"analysis_{item_id}"])

else:
    # ---------- 默认模式：原有最新内参展示 ----------
    if not history_data:
        st.warning("还没有数据。请确认 GitHub Actions 已经成功运行并写入了 Supabase。")
    else:
        with st.container(border=True):
            st.subheader(f"📌 最新深度内参：{latest.get('topic', '全球军政内参')}")
            st.caption(f"生成时间：{latest.get('time')}")
            st.divider()

            summary_text = latest.get("summary", "")
            if summary_text:
                st.markdown(summary_text)
            else:
                st.warning("最新记录里没有 summary 字段。")

        st.caption("提示：默认展示后台最新内参；在左侧输入关键词可搜索历史情报并做即时 AI 分析。")
