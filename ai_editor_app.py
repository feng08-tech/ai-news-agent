import streamlit as st
import os
import pandas as pd
import pydeck as pdk
import requests
import time
from datetime import datetime
from supabase import create_client, Client
from openai import OpenAI

st.set_page_config(page_title="全球政军情报指挥中心", page_icon="🌍", layout="wide")

# ================= 0. 极简明文密码登录模块 =================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 全球政军情报指挥中心 - 访问受限")
    st.write("请输入访问密码以查看内部情报：")
    
    password_input = st.text_input("访问密码", type="password")
    
    if st.button("登录系统", type="primary"):
        # 直接对比明文密码
        if password_input == st.secrets.get("APP_PASSWORD"):
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("❌ 密码错误，请重试（注意不要输入多余的空格）。")
            
    st.stop()  # 如果未登录，后面的代码全部停止执行

# ================= 1. 配置与连接 =================
# 走到这里说明已经登录成功
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

st.title("🌍 全球政军情报指挥中心")
st.write("后台每日自动抓取、AI 研判并写入云端；支持读取展示、历史搜索与全球媒体实时检索。")

# 侧边栏退出登录按钮
with st.sidebar:
    st.divider()
    if st.button("🚪 退出登录", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# ================= 2. 核心函数 =================
def analyze_text(text: str, focus: str = "提炼要点、判断影响、给出后续观察指标") -> str:
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

def fetch_gdelt_news(keyword: str, country_code: str = "", max_records: int = 30):
    """调用 GDELT API，包含 6 秒强制冷却限制，防止触发 429 封禁"""
    if 'last_gdelt_request' not in st.session_state:
        st.session_state['last_gdelt_request'] = 0.0

    current_time = time.time()
    elapsed = current_time - st.session_state['last_gdelt_request']
    
    if elapsed < 6.0:
        wait_time = 6.0 - elapsed
        st.info(f"⏳ 为遵守 GDELT 接口限制，强制冷却等待 {wait_time:.1f} 秒...")
        time.sleep(wait_time)

    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    query = keyword
    if country_code:
        query += f" sourcecountry:{country_code}"
        
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "sort": "datedesc"
    }
    
    try:
        st.session_state['last_gdelt_request'] = time.time()
        response = requests.get(url, params=params, timeout=(10, 60))
        
        if response.status_code == 429:
            return {"error": "❌ GDELT 接口繁忙（429），当前 IP 被限流。请休息几分钟后再试，或更换关键词。"}
            
        response.raise_for_status()
        
        try:
            data = response.json()
        except ValueError:
            return {"error": "❌ GDELT 返回了非标准数据，大概率是被临时限流。请稍等片刻再试。"}
            
        if not isinstance(data, dict) or "articles" not in data:
            return []
            
        return data["articles"]
        
    except requests.exceptions.Timeout:
        return {"error": "⏱️ GDELT 接口响应超时。该接口目前负载较高，请稍后再试。"}
    except Exception as e:
        return {"error": f"请求失败: {e}"}

# ================= 3. 侧边栏（历史库） =================
with st.sidebar:
    st.header("🔍 手动搜索（历史库）")
    keyword = st.text_input("输入历史库关键词", placeholder="例如：台海、俄乌、无人机")
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

# ================= 4. 页面主体（分 Tab） =================
tab1, tab2 = st.tabs(["📊 情报指挥中心 (历史库)", "🌐 全球媒体实时搜索 (GDELT)"])

# ---------------- Tab 1: 情报指挥中心 ----------------
with tab1:
    if history_data:
        latest = history_data[0]
        total_records = len(history_data)
        latest_time = latest.get('time', '未知')

        col1, col2, col3 = st.columns(3)
        col1.metric("云端情报总数", f"{total_records} 份")
        col2.metric("最新研判时间", latest_time)
        col3.metric("系统状态", "🟢 实时更新中")
        st.divider()

    # 地图
    st.subheader("📍 全球热点态势分布")
    hotspot_data = pd.DataFrame({
        "name": ["基辅 (俄乌)", "加沙 (中东)", "德黑兰 (伊朗)", "台海 (印太)", "哈尔科夫 (前线)", "喀土穆 (苏丹)"],
        "lat": [50.45, 31.55, 35.69, 25.03, 49.99, 15.55],
        "lon": [30.52, 35.10, 51.39, 121.56, 36.23, 32.53]
    })
    layer = pdk.Layer(
        "ScatterplotLayer", hotspot_data, get_position=["lon", "lat"],
        get_color=[255, 50, 50, 220], get_radius=80000, pickable=True,
    )
    view_state = pdk.ViewState(latitude=25, longitude=60, zoom=1.5, pitch=0)
    st.pydeck_chart(pdk.Deck(
        layers=[layer], initial_view_state=view_state,
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={"text": "📍 {name}"}
    ))
    st.divider()

    # 搜索或展示最新
    if keyword:
        kw = keyword.strip().lower()
        matched = [
            item for item in history_data
            if kw in (item.get("topic") or "").lower() or kw in (item.get("summary") or "").lower()
        ][:search_limit]

        st.subheader(f"🔍 历史库搜索结果：{keyword}（{len(matched)} 条）")
        if not matched:
            st.info("没有找到匹配内容，换个关键词试试。")
        else:
            if st.button("📝 生成主题简报", key="brief_btn"):
                material = "\n\n".join([
                    f"主题：{item.get('topic', '')}\n时间：{item.get('time', '')}\n内容：{(item.get('summary') or '')[:800]}"
                    for item in matched[:10]
                ])
                with st.spinner("正在生成主题简报..."):
                    try:
                        st.session_state["search_brief"] = analyze_text(material, focus="汇总相关动态、判断趋势、列出关键风险点和后续观察指标")
                    except Exception as e:
                        st.error(f"简报生成失败：{e}")

            if st.session_state.get("search_brief"):
                with st.container(border=True):
                    st.markdown("### 📝 主题简报")
                    st.markdown(st.session_state["search_brief"])
            st.divider()

            for item in matched:
                item_id = item.get("id")
                summary = item.get("summary") or ""
                with st.container(border=True):
                    st.subheader(f"📌 {item.get('topic', '无标题')}")
                    st.caption(f"时间：{item.get('time', '未知')}")
                    st.markdown(summary[:1000] + ("..." if len(summary) > 1000 else ""))
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
        if not history_data:
            st.warning("还没有数据。请确认 GitHub Actions 已经成功运行并写入了 Supabase。")
        else:
            with st.container(border=True):
                st.subheader(f"📌 最新深度内参：{history_data[0].get('topic', '全球军政内参')}")
                st.caption(f"生成时间：{history_data[0].get('time')}")
                st.divider()
                summary_text = history_data[0].get("summary", "")
                if summary_text:
                    st.markdown(summary_text)
                else:
                    st.warning("最新记录里没有 summary 字段。")

# ---------------- Tab 2: 全球媒体搜索 ----------------
with tab2:
    st.subheader("🌐 GDELT 全球媒体实时检索")
    st.write("检索全球 100+ 种语言的新闻报道，数据每 15 分钟更新一次。")
    st.warning("⚠️ 注意：由于 Streamlit Cloud 是共享 IP，极易被 GDELT 限流。如果一直报 429 错误，说明当前服务器 IP 被暂时封禁，请等待几小时后再试。建议使用英文关键词（如 AI, semiconductor）效果更好。")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        gdelt_keyword = st.text_input("🔍 新闻关键词（支持 OR 逻辑）", "AI OR technology")
    with col2:
        country_map = {
            "全球": "", "美国": "US", "中国": "CN", "俄罗斯": "RU", "英国": "UK",
            "日本": "JA", "德国": "GM", "法国": "FR", "印度": "IN", "乌克兰": "UP"
        }
        selected_country = st.selectbox("🌐 限定国家/地区", list(country_map.keys()))
        country_code = country_map[selected_country]
    with col3:
        gdelt_max = st.slider("📄 最大条数", 10, 100, 30, key="gdelt_slider")

    if st.button("🚀 开始抓取全球新闻", type="primary", use_container_width=True):
        if not gdelt_keyword.strip():
            st.warning("请输入关键词")
        else:
            with st.spinner("正在向 GDELT 请求全球数据（请勿连续点击）..."):
                result = fetch_gdelt_news(gdelt_keyword, country_code, gdelt_max)
                
            if isinstance(result, dict) and "error" in result:
                st.error(result["error"])
            elif not result:
                st.info("没有找到相关新闻，尝试更换关键词或国家。")
            else:
                st.success(f"共获取到 {len(result)} 条最新报道！")
                df_data = []
                for art in result:
                    raw_time = art.get("seendate", "")
                    try:
                        dt = datetime.strptime(raw_time, "%Y%m%dT%H%M%SZ")
                        formatted_time = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        formatted_time = raw_time

                    df_data.append({
                        "时间": formatted_time,
                        "标题": art.get("title", "无标题"),
                        "来源国家": art.get("sourcecountry", ""),
                        "语言": art.get("language", ""),
                        "媒体域名": art.get("domain", ""),
                        "链接": art.get("url", "")
                    })
                
                df = pd.DataFrame(df_data)
                st.dataframe(
                    df,
                    column_config={"链接": st.column_config.LinkColumn("🔗 原文链接", display_text="点击阅读")},
                    use_container_width=True,
                    hide_index=True
                )
