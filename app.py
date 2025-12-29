import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import re
from urllib.parse import urljoin

# --- 設定 ---
st.set_page_config(page_title="西宮市ごみカレンダー", page_icon="🗑️")

# ==========================================
# 1. カレンダー取得・処理機能
# ==========================================
def get_url_by_date(year, month):
    """指定した年月の公式カレンダーURLを生成する"""
    date_str = f"{year}-{month:02d}"
    # ID=466は西宮市のカレンダーID
    return f"https://www.nishi.or.jp/homepage/gomicalendar/calendar_b.html?date={date_str}&id=466#garbage-calendar"

def get_weekday_str(year, month, day):
    try:
        dt = datetime.date(year, month, int(day))
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        return weekdays[dt.weekday()]
    except ValueError:
        return ""

@st.cache_data(ttl=3600)  # 1時間キャッシュ
def fetch_calendar_data():
    """今月と来月のカレンダーデータをまとめて取得"""
    now = datetime.datetime.now()
    years_months = [(now.year, now.month)]
    
    # 来月の計算
    if now.month == 12:
        years_months.append((now.year + 1, 1))
    else:
        years_months.append((now.year, now.month + 1))
    
    all_data = []
    
    for year, month in years_months:
        url = get_url_by_date(year, month)
        try:
            response = requests.get(url, timeout=10)
            response.encoding = response.apparent_encoding
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                calendar_table = soup.find('table')
                if calendar_table:
                    rows = calendar_table.find_all('tr')
                    for row in rows:
                        cols = row.find_all('td')
                        for col in cols:
                            text = col.get_text(strip=True)
                            if text:
                                match = re.match(r"(\d+)(.*)", text)
                                if match:
                                    day_num = int(match.group(1))
                                    gomi_type = match.group(2)
                                    date_obj = datetime.date(year, month, day_num)
                                    # 過去データは除外（今日以降のみ）
                                    if date_obj >= now.date():
                                        all_data.append({
                                            "date_obj": date_obj,
                                            "日付": f"{month}/{day_num}",
                                            "曜日": get_weekday_str(year, month, day_num),
                                            "ゴミの種類": gomi_type
                                        })
        except Exception:
            pass
            
    # 日付順に並べ替え
    df = pd.DataFrame(all_data)
    if not df.empty:
        df = df.sort_values('date_obj')
    return df

# ==========================================
# 2. 分別ガイド詳細取得機能
# ==========================================
@st.cache_data(ttl=86400) # 1日キャッシュ
def fetch_detailed_guide():
    base_url = "https://www.nishi.or.jp/kurashi/gomi/gominoshushu/gominobunnbetu.html"
    guide_data = []
    try:
        res = requests.get(base_url, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        
        content_area = soup.find('div', id='main') or soup.find('div', id='contents')
        if not content_area: return []

        links = content_area.find_all('a')
        target_urls = []
        for link in links:
            href = link.get('href')
            text = link.get_text(strip=True)
            if href and text:
                keywords = ["もやすごみ", "燃やさないごみ", "資源", "ペットボトル", "プラ", "危険"]
                if any(k in text for k in keywords):
                    full_url = urljoin(base_url, href)
                    target_urls.append((text, full_url))
        
        target_urls = list(set(target_urls))

        for title, link_url in target_urls:
            try:
                sub_res = requests.get(link_url, timeout=5)
                sub_res.encoding = sub_res.apparent_encoding
                sub_soup = BeautifulSoup(sub_res.text, 'html.parser')
                sub_content = sub_soup.find('div', id='main') or sub_soup.find('div', id='contents')
                if sub_content:
                    for script in sub_content(["script", "style"]):
                        script.decompose()
                    details_text = sub_content.get_text("\n", strip=True)
                    mapped_category = map_guide_to_calendar(title)
                    guide_data.append({
                        "category_name": title,
                        "calendar_name": mapped_category,
                        "details": details_text,
                        "url": link_url
                    })
            except Exception:
                continue
        return guide_data
    except Exception:
        return []

def map_guide_to_calendar(guide_title):
    mapping = {
        "もやすごみ": "燃やすごみ", "燃やさないごみ": "燃やさないごみ",
        "資源A": "資源A", "資源B": "資源B",
        "その他プラ": "その他プラ", "ペットボトル": "ペットボトル",
    }
    for key, val in mapping.items():
        if key in guide_title: return val
    return guide_title

# ==========================================
# 3. メイン表示処理
# ==========================================
def main():
    st.title("🗑️ 西宮市 ごみ収集ナビ")

    with st.spinner('データを更新しています...'):
        df_calendar = fetch_calendar_data()
        guide_list = fetch_detailed_guide()

    tab1, tab2 = st.tabs(["📅 カレンダー", "🔍 分別・検索"])

    # -----------------------
    # タブ1: カレンダー
    # -----------------------
    with tab1:
        # 公式サイトへのリンク
        now = datetime.datetime.now()
        current_month_url = get_url_by_date(now.year, now.month)
        st.markdown(f"**公式サイトで確認:** [👉 西宮市ごみカレンダー ({now.month}月分)]({current_month_url})")

        if df_calendar is not None and not df_calendar.empty:
            today_date = now.date()
            
            # 今日以降のデータだけを使う
            future_df = df_calendar[df_calendar['date_obj'] >= today_date]

            if not future_df.empty:
                # === 今日の収集 ===
                today_df = future_df[future_df['date_obj'] == today_date]
                if not today_df.empty:
                    row = today_df.iloc[0]
                    st.markdown("### 📅 今日の収集")
                    st.success(f"**今日は {row['日付']} ({row['曜日']})**")
                    st.markdown(f"<h1 style='text-align: center; color: #ff4b4b;'>{row['ゴミの種類']}</h1>", unsafe_allow_html=True)
                else:
                    next_row = future_df.iloc[0]
                    st.info(f"今日は収集がありません。次は {next_row['日付']} ({next_row['曜日']}) の {next_row['ゴミの種類']} です。")
                
                st.divider()
                
                # データ分割：向こう1週間 (7件) と それ以降
                one_week_df = future_df.head(7)
                rest_df = future_df.iloc[7:]

                # === 向こう1週間の予定 ===
                st.subheader("📋 向こう1週間の予定")
                st.table(one_week_df[['日付', '曜日', 'ゴミの種類']].set_index('日付'))

                # === ★復活: 次回以降のイレギュラーごみ ===
                st.subheader("👀 次回以降の予定 (1週間以内にないもの)")
                
                types_in_week = set(one_week_df['ゴミの種類'].unique())
                types_in_rest = set(rest_df['ゴミの種類'].unique())
                
                # 「未来にはある」けど「直近1週間にはない」ゴミ
                missing_types = types_in_rest - types_in_week
                
                if missing_types:
                    found_count = 0
                    for g_type in missing_types:
                        # そのゴミの最短の日付を探す
                        next_match = rest_df[rest_df['ゴミの種類'] == g_type]
                        if not next_match.empty:
                            next_row = next_match.iloc[0]
                            st.info(f"**{g_type}** は、少し先の **{next_row['日付']} ({next_row['曜日']})** です")
                            found_count += 1
                    
                    if found_count == 0:
                         st.caption("※これ以外の収集予定は今のところありません。")
                else:
                    st.caption("※主要なゴミはすべて1週間以内に収集があります。")

            else:
                 st.warning("これ以降の収集予定が見つかりませんでした。")

        else:
            st.error("カレンダーデータが取得できませんでした。")
            st.link_button("公式サイトを直接見る", current_month_url)

    # -----------------------
    # タブ2: 分別ガイド
    # -----------------------
    with tab2:
        st.header("🔍 ごみ分別検索")
        query = st.text_input("検索キーワード (例: 電池, フライパン)", "")

        if query:
            found_count = 0
            for item in guide_list:
                if query in item['details'] or query in item['category_name']:
                    found_count += 1
                    cat_name = item['category_name']
                    cal_name = item['calendar_name']
                    
                    with st.container():
                        st.markdown(f"### 💡 {cat_name} の可能性があります")
                        
                        if df_calendar is not None and not df_calendar.empty:
                            # 今日以降のカレンダーから探す
                            matches = df_calendar[
                                (df_calendar['ゴミの種類'].str.contains(cal_name, na=False)) &
                                (df_calendar['date_obj'] >= datetime.datetime.now().date())
                            ]
                            if not matches.empty:
                                next_pickup = matches.iloc[0]
                                st.success(f"**次の収集日:** 📅 **{next_pickup['日付']} ({next_pickup['曜日']})**")
                        
                        with st.expander("詳しい出し方を見る"):
                            st.markdown(f"[公式ページで見る]({item['url']})")
                            preview = item['details'][:300] + "..." if len(item['details']) > 300 else item['details']
                            st.text(preview)
                        st.divider()
            if found_count == 0:
                st.warning(f"「{query}」は見つかりませんでした。")
        else:
            st.info("キーワードを入力すると結果が表示されます。")
            with st.expander("カテゴリ一覧"):
                for item in guide_list:
                    st.write(f"- [{item['category_name']}]({item['url']})")

if __name__ == "__main__":
    main()