import streamlit as st
import os
import pandas as pd
import pydeck as pdk
import requests
import time
from datetime import datetime
import psycopg2
from urllib.parse import urlparse, urlunparse
from openai import OpenAI

st.set_page_config(page_title="全球政军情报指挥中心", page_icon="🌍", layout="wide")

# ================= 0. 极简密码登录 =================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 全球政军情报指挥中心 - 访问受限")
    password_input = st.text_input("请输入访问密码：", type="password")
    if st.button("登录系统", type="primary"):
        if password_input == st.secrets.get("APP_PASSWORD", "123456"):
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("❌ 密码错误。")
    st.stop()

# ================= 1. 配置（使用连接池） =================
# ⚠️ 请将下方字符串替换为你从 Supabase 复制的 Session pooler 连接串
DATABASE_URL = st.secrets.get("DATABASE_URL")
deepseek_key = st.secrets.get("DEEPSEEK_API_KEY", "")

if not DATABASE_URL:
    st.error("⚠️ 配置缺失：请在 Secrets 中添加 DATABASE_URL。")
    st.stop()

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
except Exception as e:
    st.error(f"❌ 数据库连接失败: {e}")
    st.stop()

st.title("🌍 全球政军情报指挥中心")
st.write("后台每日自动抓取、AI 研判并写入云端；支持读取展示、历史搜索与全球媒体实时检索。")

with st.sidebar:
    st.divider()
    if st.button("🚪 退出登录", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# ================= 2. 核心函数 =================
def analyze_text(text: str, focus: str = "提炼要点、判断影响") -> str:
    if not deepseek_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY。")
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

def fetch_gdelt_news(keyword: str, country_code: str = "", max_records: int = 30):
    if 'last_gdelt_request' not in st.session_state:
        st.session_state['last_gdelt_request'] = 0.0
    elapsed = time.time() - st.session_state['last_gdelt_request']
    if elapsed < 6.0:
        time.sleep(6.0 - elapsed)
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    query = keyword + (f" sourcecountry:{country_code}" if country_code else "")
    params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": str(max_records), "sort": "datedesc"}
    try:
        st.session_state['last_gdelt_request'] = time.time()
        response = requests.get(url, params=params, timeout=(10, 60))
        if response.status_code == 429: return {"error": "❌ GDELT 接口繁忙，请稍后再试。"}
        response.raise_for_status()
        try: data = response.json()
        except ValueError: return {"error": "❌ GDELT 返回非标准数据，可能被限流。"}
        if not isinstance(data, dict) or "articles" not in data: return []
        return data["articles"]
    except Exception as e: return {"error": f"请求失败: {e}"}

# ================= 3. 侧边栏（历史库） =================
with st.sidebar:
    st.header("🔍 手动搜索（历史库）")
    keyword = st.text_input("输入历史库关键词", placeholder="例如：台海、俄乌")
    search_limit = st.slider("最多显示条数", 5, 50, 20)
    st.divider()

    st.header("☁️ 历史情报库")
    history_data = []
    try:
        cursor.execute("SELECT * FROM history ORDER BY time DESC;")
        columns = [desc[0] for desc in cursor.description]
        history_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        st.error(f"读取数据失败: {e}")
        # 打印详细错误帮助排查
        st.write(f"👉 **尝试连接的地址:** `{urlparse(DATABASE_URL).netloc}`")

    if not history_data:
        st.info("暂无历史记录。")
    else:
        for item in history_data:
            with st.expander(f"🕒 {item.get('time', '未知时间')}"):
                text_preview = item.get("summary") or item.get("topic") or item.get("content") or "无内容"
                st.markdown(str(text_preview)[:300] + "...")
                if st.button("🗑️ 删除", key=f"del_{item.get('id')}"):
                    try:
                        cursor.execute("DELETE FROM history WHERE id = %s;", (item.get('id'),))
                        conn.commit()
                        st.rerun()
                    except Exception as e:
                        st.error(f"删除失败: {e}")

# ================= 4. 页面主体 =================
tab1, tab2 = st.tabs(["📊 情报指挥中心 (历史库)", "🌐 全球媒体实时搜索 (GDELT)"])

with tab1:
    if history_data:
        latest = history_data[0]
        col1, col2, col3 = st.columns(3)
        col1.metric("云端情报总数", f"{len(history_data)} 份")
        col2.metric("最新研判时间", latest.get('time', '未知'))
        col3.metric("系统状态", "🟢 实时更新中")
        st.divider()

    st.subheader("📍 全球热点态势分布")
    hotspot_data = pd.DataFrame({
        "name": ["基辅 (俄乌)", "加沙 (中东)", "德黑兰 (伊朗)", "台海 (印太)", "哈尔科夫 (前线)", "喀土穆 (苏丹)"],
        "lat": [50.45, 31.55, 35.69, 25.03, 49.99, 15.55],
        "lon": [30.52, 35.10, 51.39, 121.56, 36.23, 32.53]
    })
    layer = pdk.Layer("ScatterplotLayer", hotspot_data, get_position=["lon", "lat"], get_color=[255, 50, 50, 220], get_radius=80000, pickable=True)
    view_state = pdk.ViewState(latitude=25, longitude=60, zoom=1.5, pitch=0)
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json", tooltip={"text": "📍 {name}"}))
    st.divider()

    if keyword:
        kw = keyword.strip().lower()
        matched = [item for item in history_data if kw in str(item.get("topic") or "").lower() or kw in str(item.get("summary") or "").lower() or kw in str(item.get("content") or "").lower()][:search_limit]

        st.subheader(f"🔍 历史库搜索结果：{keyword}（{len(matched)} 条）")
        if not matched:
            st.info("没有找到匹配内容。")
        else:
            if st.button("📝 生成主题简报", key="brief_btn"):
                material = "\n\n".join([f"主题：{item.get('topic', '')}\n内容：{str(item.get('summary') or item.get('content') or '')[:800]}" for item in matched[:10]])
                with st.spinner("正在生成主题简报..."):
                    try: st.session_state["search_brief"] = analyze_text(material, focus="汇总相关动态、判断趋势")
                    except Exception as e: st.error(f"简报生成失败：{e}")

            if st.session_state.get("search_brief"):
                with st.container(border=True):
                    st.markdown("### 📝 主题简报")
                    st.markdown(st.session_state["search_brief"])
            st.divider()

            for item in matched:
                item_id = item.get("id")
                full_text = str(item.get("summary") or item.get("content") or item.get("topic") or "")
                with st.container(border=True):
                    st.subheader(f"📌 {item.get('topic', '无标题')}")
                    st.caption(f"时间：{item.get('time', '未知')}")
                    st.markdown(full_text[:1000] + ("..." if len(full_text) > 1000 else ""))
                    if st.button("🤖 AI 分析这条", key=f"ai_{item_id}"):
                        with st.spinner("分析中..."):
                            try: st.session_state[f"analysis_{item_id}"] = analyze_text(full_text)
                            except Exception as e: st.error(f"分析失败：{e}")
                    if st.session_state.get(f"analysis_{item_id}"):
                        st.markdown("#### 🤖 AI 分析")
                        st.markdown(st.session_state[f"analysis_{item_id}"])
    else:
        if not history_data:
            st.warning("还没有数据。")
        else:
            with st.container(border=True):
                latest_text = str(history_data[0].get("summary") or history_data[0].get("topic") or history_data[0].get("content") or "暂无内容")
                st.subheader(f"📌 最新深度内参：{history_data[0].get('topic', '全球军政内参')}")
                st.caption(f"生成时间：{history_data[0].get('time')}")
                st.divider()
                st.markdown(latest_text)

with tab2:
    st.subheader("🌐 GDELT 全球媒体实时检索")
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1: gdelt_keyword = st.text_input("🔍 新闻关键词", "AI OR technology")
    with col2:
        country_map = {"全球": "", "美国": "US", "中国": "CN", "俄罗斯": "RU", "英国": "UK", "日本": "JA", "德国": "GM", "法国": "FR", "印度": "IN", "乌克兰": "UP"}
        country_code = country_map[st.selectbox("🌐 限定国家", list(country_map.keys()))]
    with col3: gdelt_max = st.slider("📄 最大条数", 10, 100, 30)

    if st.button("🚀 开始抓取", type="primary", use_container_width=True):
        with st.spinner("正在向 GDELT 请求..."):
            result = fetch_gdelt_news(gdelt_keyword, country_code, gdelt_max)
        if isinstance(result, dict) and "error" in result: st.error(result["error"])
        elif not result: st.info("没有找到相关新闻。")
        else:
            st.success(f"共获取到 {len(result)} 条！")
            df_data = []
            for art in result:
                raw_time = art.get("seendate", "")
                try: formatted_time = datetime.strptime(raw_time, "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%d %H:%M")
                except: formatted_time = raw_time
                df_data.append({"时间": formatted_time, "标题": art.get("title", "无标题"), "来源": art.get("sourcecountry", ""), "链接": art.get("url", "")})
            st.dataframe(pd.DataFrame(df_data), column_config={"链接": st.column_config.LinkColumn("🔗 原文链接", display_text="点击阅读")}, use_container_width=True)

# 关闭数据库连接
if 'conn' in locals() and conn:
    cursor.close()
    conn.close()
