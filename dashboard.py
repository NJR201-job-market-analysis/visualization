import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from st_aggrid import AgGrid, GridOptionsBuilder
from dotenv import load_dotenv
import os
from collections import Counter
from datetime import datetime, timedelta

# --- Session State Initialization ---
if 'page_number' not in st.session_state:
    st.session_state.page_number = 0
if 'current_skill' not in st.session_state:
    st.session_state.current_skill = None


# --- 載入資料並預處理 ---
@st.cache_data
def load_data():
    # 從 Parquet 檔案讀取數據，而不是資料庫
    df = pd.read_parquet("./jobs_data.parquet")

    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    # 薪資標準化 (優化版)
    def normalize_and_clean_salary(row):
        salary_min = row['salary_min']
        salary_max = row['salary_max']
        salary_type = row['salary_type']

        if pd.isna(salary_min):
            return None

        # 步驟 1: 如果提供有效的薪資範圍，則使用平均值
        base_salary = salary_min
        if pd.notna(salary_max) and salary_max > salary_min:
            base_salary = (salary_min + salary_max) / 2

        # 步驟 2: 根據薪資類型進行標準化
        normalized_salary = base_salary
        if salary_type == "年薪":
            normalized_salary = base_salary / 12
        elif salary_type == "日薪":
            # 對標示錯誤的日薪進行健全性檢查
            if base_salary > 20000:
                normalized_salary = base_salary
            else:
                normalized_salary = base_salary * 22
        elif salary_type == "時薪":
            # 對標示錯誤的時薪進行健全性檢查
            if base_salary > 2000:
                normalized_salary = base_salary
            else:
                normalized_salary = base_salary * 176
        
        # 步驟 3: 對極高的月薪進行最終健全性檢查 (可能為誤標的年薪)
        if pd.notna(normalized_salary) and normalized_salary > 500000:
            return normalized_salary / 12

        return normalized_salary

    df["monthly_salary"] = df.apply(normalize_and_clean_salary, axis=1)
    
    # 使用 aggregated_skills 計算技能數量
    df["skills_count"] = (
        df["aggregated_skills"].fillna("").apply(lambda x: len(x.split(",")) if x else 0)
    )
    # 為了後續圖表相容性，如果 aggregated_skills 存在，就用它覆蓋舊的 required_skills
    if "aggregated_skills" in df.columns:
        df["required_skills"] = df["aggregated_skills"]
        
    return df


# --- 主程式邏輯 ---
st.set_page_config(page_title="就業市場 Dashboard", layout="wide")

# st.title("📊 就業市場總覽")

df = load_data()

# Fill missing city data with '遠端工作' to prevent them from being filtered out
df['city'] = df['city'].fillna('遠端工作')

# --- Sidebar Filters ---
st.sidebar.header("篩選器")

# --- 統一城市名稱 ---
city_name_map = {
    '台北市': '臺北市',
    '台中市': '臺中市',
    '台南市': '臺南市',
    '台東縣': '臺東縣',
    '新竹市': '新竹',
    '新竹縣': '新竹'
}
df['city'] = df['city'].replace(city_name_map)

selected_platform = st.sidebar.multiselect(
    "平台",
    options=df["platform"].unique(),
    default=df["platform"].unique(),
)

# 定義台灣城市列表，用於過濾篩選器選項
TAIWAN_CITIES = [
    '臺北市', '新北市', '桃園市', '臺中市', '臺南市', '高雄市', '基隆市', '新竹', '嘉義市',
    '苗栗縣', '彰化縣', '南投縣', '雲林縣', '嘉義縣', '屏東縣', '宜蘭縣', '花蓮縣',
    '臺東縣', '澎湖縣', '金門縣', '連江縣', '遠端工作'
]

# 從 DataFrame 中取得所有城市，並篩選出台灣的城市
available_cities = df['city'].dropna().unique()
taiwan_cities_in_df = sorted([city for city in available_cities if city in TAIWAN_CITIES])

selected_city = st.sidebar.multiselect(
    "城市",
    options=taiwan_cities_in_df,
    default=taiwan_cities_in_df,
)

# --- Define categories to exclude from all analyses ---
EXCLUDED_CATEGORIES = [
    '其他資訊專業人員',
    'UI/UX設計師',
    'MIS工程師',
    'MES工程師',
    '網路安全分析師',
    '網路管理工程師'
]

df_filtered = df[
    df["platform"].isin(selected_platform) &
    df["city"].isin(selected_city) &
    ~df["category_name"].isin(EXCLUDED_CATEGORIES)
]

# --- Globally exclude '面議' jobs defaulted to 40k for more accurate analysis ---
df_filtered = df_filtered[~((df_filtered['salary_type'] == '面議') & (df_filtered['monthly_salary'] == 40000))]


# Define a global constant for salary filtering
MAX_REASONABLE_SALARY = 200000


# --- KPI Cards ---
col1, col2, col3, col4 = st.columns(4)

# 1. Total Jobs
col1.metric("📌 職缺總數", f"{len(df_filtered):,}")

# 2. Recruiting Companies
num_companies = df_filtered['company_name'].nunique()
col2.metric("🏢 徵才公司數", f"{num_companies:,}")

# 3. Median Salary
salary_df_for_median = df_filtered.dropna(subset=['monthly_salary'])
salary_df_for_median = salary_df_for_median[salary_df_for_median['monthly_salary'] < MAX_REASONABLE_SALARY]
# 排除薪資為 40000 且類型為「面議」的職缺，以計算更真實的中位數
adjusted_salary_df = salary_df_for_median[~((salary_df_for_median['salary_type'] == '面議') & (salary_df_for_median['monthly_salary'] == 40000))]
median_salary = adjusted_salary_df['monthly_salary'].median() if not adjusted_salary_df.empty else 0
col3.metric("💵 薪資中位數 (月)", f"{median_salary:,.0f} 元")

# 4. Median Experience Requirement
exp_df_for_median = df_filtered.copy()
exp_df_for_median['experience_min'] = pd.to_numeric(exp_df_for_median['experience_min'], errors='coerce')
exp_df_for_median = exp_df_for_median.dropna(subset=['experience_min'])
median_exp = exp_df_for_median['experience_min'].median() if not exp_df_for_median.empty else 0
col4.metric("📈 經驗要求中位數 (年)", f"{median_exp:.1f} 年")


st.divider()

# --- Market Overview ---

c1, c2 = st.columns(2)

with c1:
    # 1. Job count per platform (Rebuilt with plotly.graph_objects to fix display bug)
    platform_df = df_filtered.dropna(subset=['platform'])
    platform_df['platform'] = platform_df['platform'].astype(str)
    platform_counts = platform_df["platform"].value_counts().reset_index()
    platform_counts.columns = ["platform", "count"]
    
    fig_platform = go.Figure(data=[go.Bar(
        x=platform_counts['platform'],
        y=platform_counts['count'],
        text=platform_counts['count'],
        textposition='outside',
        texttemplate='%{text:,.0f}'
    )])
    
    fig_platform.update_layout(
        title_text='各平台職缺數量',
        xaxis_title='平台',
        yaxis_title='職缺數',
        xaxis={'categoryorder':'total descending'}
    )
    st.plotly_chart(fig_platform, use_container_width=True)

with c2:
    # 2. Job count per city (Top 10)
    city_df = df_filtered["city"].dropna().value_counts().nlargest(10).reset_index()
    city_df.columns = ["city", "count"]
    fig_city = px.bar(
        city_df,
        y="count",
        x="city",
        title="各城市職缺數量 (Top 10)",
        labels={'city': '城市', 'count': '職缺數'},
        text='count'
    )
    fig_city.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig_city.update_layout(xaxis={'categoryorder':'total descending'})
    st.plotly_chart(fig_city, use_container_width=True)

c3, c4 = st.columns(2)

with c3:
    # Top Paying Categories
    cat_counts = df_filtered['category_name'].value_counts()
    valid_categories = cat_counts[cat_counts >= 5].index
    high_paying_cat_df = df_filtered[df_filtered['category_name'].isin(valid_categories)].copy()
    high_paying_cat_df = high_paying_cat_df[high_paying_cat_df['monthly_salary'] < MAX_REASONABLE_SALARY]
    # Exclude '面議' jobs recorded as 40000 to get a more accurate median salary
    high_paying_cat_df = high_paying_cat_df[~((high_paying_cat_df['salary_type'] == '面議') & (high_paying_cat_df['monthly_salary'] == 40000))]
    top_paying_categories = high_paying_cat_df.groupby('category_name')['monthly_salary'].median().nlargest(10).reset_index()
    top_paying_categories.columns = ['category', 'median_salary']
    fig_top_cat = px.bar(
        top_paying_categories.sort_values('median_salary', ascending=True),
        x='median_salary',
        y='category',
        orientation='h',
        title="Top 10 高薪職缺分類",
        labels={'category': '職缺分類', 'median_salary': '薪資中位數 (元)'},
        text='median_salary'
    )
    fig_top_cat.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig_top_cat.update_layout(title_font_size=16, height=450)
    st.plotly_chart(fig_top_cat, use_container_width=True)

with c4:
    # Popular Cities Salary Range Comparison
    top_cities_for_salary = df_filtered['city'].value_counts().nlargest(5).index
    city_salary_df = df_filtered[df_filtered['city'].isin(top_cities_for_salary)].copy()
    city_salary_df = city_salary_df.dropna(subset=['monthly_salary'])
    city_salary_df = city_salary_df[city_salary_df['monthly_salary'] < MAX_REASONABLE_SALARY]
    # Exclude '面議' jobs recorded as 40000 to get a more accurate salary range
    city_salary_df = city_salary_df[~((city_salary_df['salary_type'] == '面議') & (city_salary_df['monthly_salary'] == 40000))]

    if not city_salary_df.empty:
        salary_quantiles = city_salary_df.groupby('city')['monthly_salary'].quantile([0.25, 0.5, 0.75]).unstack().reset_index()
        salary_quantiles.columns = ['city', '低標 (25%)', '中位數 (50%)', '高標 (75%)']
        salary_quantiles_melted = salary_quantiles.melt(
            id_vars='city', 
            var_name='薪資指標', 
            value_name='月薪'
        )
        fig_city_salary_range = px.bar(
            salary_quantiles_melted,
            x='city',
            y='月薪',
            color='薪資指標',
            barmode='group',
            title='熱門城市薪資範圍比較 (Top 5)',
            labels={'city': '城市', '月薪': '月薪 (元)'},
            text='月薪'
        )
        fig_city_salary_range.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        fig_city_salary_range.update_layout(height=450)
        st.plotly_chart(fig_city_salary_range, use_container_width=True)
    else:
        st.write("無足夠資料可進行城市薪資分析。")


# --- 城市職缺分類佔比 (優化版) ---
top_cities_for_dist = df_filtered['city'].value_counts().nlargest(5).index
city_category_df_for_dist = df_filtered[df_filtered['city'].isin(top_cities_for_dist)].copy()

# Merge categories for this chart specifically
city_category_df_for_dist['category_name'] = city_category_df_for_dist['category_name'].replace({'網站開發人員': '前端工程師'})
city_category_df_for_dist = city_category_df_for_dist[city_category_df_for_dist['category_name'] != '未分類']
    
# --- Bug Fix: Calculate top categories based on the ENTIRE filtered dataset ---
# This ensures major roles like '雲端工程師' are not missed
top_9_categories_overall = df_filtered['category_name'].value_counts().nlargest(9).index

# Group less frequent categories into '其他'
city_category_df_for_dist['display_category'] = city_category_df_for_dist['category_name'].apply(
    lambda x: x if x in top_9_categories_overall else '其他'
)

city_category_summary = city_category_df_for_dist.groupby(['city', 'display_category']).size().reset_index(name='count')

# Calculate percentage
city_sums = city_category_summary.groupby('city')['count'].transform('sum')
city_category_summary['percentage'] = (100 * city_category_summary['count'] / city_sums).round(1)

fig_city_category = px.bar(
    city_category_summary,
    x='city',
    y='percentage',
    color='display_category',
    title='熱門城市職缺分類佔比 (Top 5 城市, Top 9 分類)',
    labels={'city': '城市', 'percentage': '職缺佔比 (%)', 'display_category': '職缺分類'},
    barmode='stack'
)
st.plotly_chart(fig_city_category, use_container_width=True)


# 1. Merge '網站開發人員' into '前端工程師'
category_dist_df = df_filtered.copy()
category_dist_df['category_name'] = category_dist_df['category_name'].replace({'網站開發人員': '前端工程師'})
    
# 2. Filter out '未分類'
category_dist_df = category_dist_df[category_dist_df['category_name'] != '未分類']
    
# 3. Get top 20 categories
top_20_dist = category_dist_df['category_name'].value_counts().nlargest(20).reset_index()
top_20_dist.columns = ['category', 'count']

fig_all_cat_dist = px.bar(
    top_20_dist.sort_values('count', ascending=True),
    x='count',
    y='category',
    orientation='h',
    title='全市場職缺分類佔比 (Top 20)',
    labels={'category': '職缺分類', 'count': '職缺數'},
    text='count'
)
fig_all_cat_dist.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
fig_all_cat_dist.update_layout(height=600)
st.plotly_chart(fig_all_cat_dist, use_container_width=True)


# --- Skill Processing Definitions ---
skill_merge_map = {
    'html5': 'HTML', 'html': 'HTML',
    'go': 'Go', 'golang': 'Go',
    'restful': 'RESTful API', 'restfulapi': 'RESTful API',
    'node': 'Node.js', 'nodejs': 'Node.js',
    'css': 'CSS', 'css3': 'CSS',
    'c語言': 'C' # 將 'C語言' 統一對應到 'C'
}
excluded_skills = {
    'git', 'linux', 'agile', 'ci/cd', 'github', 'gitlab', 'jenkins', 
    'restful api', 'shell script', 'scrum',
    'c' # 精準排除因關鍵字 'C' 造成的噪聲
}

def process_skills(skills_list):
    processed_skills = []
    for s in skills_list:
        s_stripped = s.strip()
        s_lower = s_stripped.lower()
        if s_lower:
            s_merged = skill_merge_map.get(s_lower, s_stripped)
            if s_merged.lower() not in excluded_skills:
                processed_skills.append(s_merged)
    return processed_skills


st.divider()

# --- Skill Analysis ---
st.subheader("💡 熱門職務技能解析")

# Add a selectbox to filter by category
# Get all categories with a reasonable number of jobs (>= 5) to provide a complete list
all_cat_counts_for_skills = df_filtered['category_name'].dropna().value_counts()
available_categories_for_skills = all_cat_counts_for_skills[all_cat_counts_for_skills >= 5].index.tolist()

# Set '後端工程師' as default if available
default_category = '後端工程師'
default_category_index = available_categories_for_skills.index(default_category) if default_category in available_categories_for_skills else 0

selected_category = st.selectbox(
    "選擇職缺分類來查看技能需求",
    options=available_categories_for_skills,
    index=default_category_index
)

if selected_category:
    # Filter dataframe by the selected category
    category_df = df_filtered[df_filtered['category_name'] == selected_category]

    c3, c4 = st.columns(2)
    with c3:
        # --- Popular Skills Treemap ---
        skills_flat_raw = category_df["required_skills"].dropna().str.cat(sep=",").split(",")
        skills_flat = process_skills(skills_flat_raw)
        skill_counts = Counter(skills_flat)
        skill_df = pd.DataFrame(skill_counts.items(), columns=["skill", "count"]).sort_values(
            by="count", ascending=False
        ).nlargest(15, 'count')

        if not skill_df.empty:
            fig_skills_treemap = px.treemap(
                skill_df,
                path=[px.Constant(f"{selected_category} 熱門技能"), 'skill'],
                values='count',
                title=f'<b>{selected_category}</b> 熱門技能分佈',
                color_continuous_scale='Blues'
            )
            fig_skills_treemap.update_traces(hovertemplate='<b>%{label}</b><br>職缺數: %{value}<extra></extra>')
            fig_skills_treemap.update_layout(margin = dict(t=50, l=25, r=25, b=25))
            st.plotly_chart(fig_skills_treemap, use_container_width=True)
        else:
            st.write(f"在 <b>{selected_category}</b> 分類中無足夠技能資料可分析。", unsafe_allow_html=True)

    with c4:
        # --- Skill Salary Analysis within Category ---
        skills_salary_df = category_df.dropna(subset=['required_skills', 'monthly_salary'])
        skills_salary_df = skills_salary_df[skills_salary_df['monthly_salary'] < MAX_REASONABLE_SALARY]
        skills_salary_df = skills_salary_df[skills_salary_df['monthly_salary'] > 0]
        
        skills_list = []
        if not skills_salary_df.empty:
            for index, row in skills_salary_df.iterrows():
                skills_raw = row['required_skills'].split(',')
                skills = process_skills(skills_raw)
                for skill in skills:
                    skills_list.append({'skill': skill, 'monthly_salary': row['monthly_salary']})
        
        if skills_list:
            skills_exploded_df = pd.DataFrame(skills_list)
            skill_analysis = skills_exploded_df.groupby('skill')['monthly_salary'].agg(['mean', 'count']).reset_index()
            skill_analysis = skill_analysis.rename(columns={'mean': 'avg_salary'})

            # 將平均薪資四捨五入至整數，以利閱讀
            skill_analysis['avg_salary'] = skill_analysis['avg_salary'].round(0).astype(int)

            # Get top skills from the treemap data to ensure consistency
            top_skills_in_category = skill_df['skill'].tolist()
            skill_analysis_top = skill_analysis[skill_analysis['skill'].isin(top_skills_in_category)]
            skill_analysis_top = skill_analysis_top.sort_values(by='avg_salary', ascending=True)

            if not skill_analysis_top.empty:
                fig_skill_salary = px.bar(
                    skill_analysis_top,
                    x='avg_salary',
                    y='skill',
                    orientation='h',
                    title=f'<b>{selected_category}</b> 熱門技能平均薪資',
                    labels={'skill': '技能', 'avg_salary': '平均月薪'},
                    text='avg_salary'
                )
                fig_skill_salary.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                st.plotly_chart(fig_skill_salary, use_container_width=True)
            else:
                st.write(f"在 <b>{selected_category}</b> 分類中無足夠薪資資料可分析。", unsafe_allow_html=True)
        else:
            st.write(f"在 <b>{selected_category}</b> 分類中無足夠薪資資料可分析。", unsafe_allow_html=True)


st.divider()
# --- Skill Reverse Lookup ---
st.subheader("💡 技能與就業機會解析")
# Create a list of top skills for the selectbox
all_skills_flat_raw = df_filtered["required_skills"].dropna().str.cat(sep=",").split(",")
all_skills_flat = process_skills(all_skills_flat_raw)
all_skill_counts = Counter(all_skills_flat)
top_50_skills = [skill for skill, count in all_skill_counts.most_common(50)]

# Set 'Java' as default if available
skill_options = sorted(top_50_skills)
default_skill = 'Java'
default_skill_index = skill_options.index(default_skill) if default_skill in skill_options else 0

selected_skill_lookup = st.selectbox(
    "選擇一個技能來查詢相關職缺分類與範例",
    options=skill_options,
    index=default_skill_index
)

if selected_skill_lookup:
    # A more robust way to check for skill presence
    def skill_in_row(skill_list_str, target_skill):
        if pd.isna(skill_list_str):
            return False
        skills = [s.strip().lower() for s in skill_list_str.split(',')]
        return target_skill.lower() in skills

    skill_lookup_df = df_filtered[df_filtered['required_skills'].apply(lambda x: skill_in_row(x, selected_skill_lookup))].copy()

    if not skill_lookup_df.empty:
        s_col1, s_col2 = st.columns([1, 1])

        with s_col1:
            category_counts = skill_lookup_df['category_name'].dropna().value_counts().nlargest(10).reset_index()
            category_counts.columns = ['category', 'count']
            
            fig_skill_cat = px.bar(
                category_counts,
                x='count',
                y='category',
                orientation='h',
                title=f"'{selected_skill_lookup}' 的 Top 10 職缺分類",
                labels={'category': '職缺分類', 'count': '職缺數'}
            )
            fig_skill_cat.update_layout(yaxis={'categoryorder':'total ascending'}, title_font_size=16)
            st.plotly_chart(fig_skill_cat, use_container_width=True)

        with s_col2:
            st.markdown(f"##### 探索 '{selected_skill_lookup}' 相關職缺")

            # --- Filters ---
            search_term = st.text_input(
                "搜尋職稱或公司", 
                key=f"search_{selected_skill_lookup}"
            )
            
            available_cities = sorted(skill_lookup_df['city'].dropna().unique())
            selected_cities = st.multiselect(
                "篩選城市", 
                options=available_cities, 
                key=f"city_{selected_skill_lookup}"
            )

            # --- Apply Filters ---
            filtered_jobs = skill_lookup_df.copy()
            if search_term:
                filtered_jobs = filtered_jobs[
                    filtered_jobs['job_title'].str.contains(search_term, case=False, na=False) |
                    filtered_jobs['company_name'].str.contains(search_term, case=False, na=False)
                ]
            if selected_cities:
                filtered_jobs = filtered_jobs[filtered_jobs['city'].isin(selected_cities)]

            # Sort by creation date
            filtered_jobs = filtered_jobs.sort_values('created_at', ascending=False)
            
            # --- Pagination Logic ---
            if st.session_state.current_skill != selected_skill_lookup:
                st.session_state.page_number = 0
                st.session_state.current_skill = selected_skill_lookup

            page_size = 5
            total_jobs = len(filtered_jobs)
            total_pages = (total_jobs // page_size) + (1 if total_jobs % page_size > 0 else 0)
            start_idx = st.session_state.page_number * page_size
            end_idx = min(start_idx + page_size, total_jobs)

            paginated_jobs = filtered_jobs.iloc[start_idx:end_idx]

            # --- Display Jobs ---
            st.markdown(f"找到 **{total_jobs}** 筆職缺")
            if total_jobs == 0:
                st.info("無符合條件的職缺。")
            
            for _, row in paginated_jobs.iterrows():
                salary_display = f"{row['monthly_salary']:,.0f} 元" if pd.notna(row['monthly_salary']) else "面議"
                st.markdown(
                    f"""
                    <div style="border: 1px solid #333; border-radius: 5px; padding: 10px; margin-bottom: 10px;">
                        <a href="{row['job_url']}" target="_blank" style="text-decoration: none; color: #1E90FF; font-weight: bold;">{row['job_title']}</a>
                        <p style="margin: 5px 0;">
                            <span style="font-style: italic;">{row['company_name']} - {row['city']}</span> | 
                            <span style="font-weight: bold; color: #FF4B4B;">{salary_display}</span>
                        </p>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
            
            # --- Pagination Controls ---
            if total_pages > 1:
                p_col1, p_col2, p_col3 = st.columns([2, 3, 2])
                with p_col1:
                    if st.session_state.page_number > 0:
                        if st.button("⬅️ 上一頁"):
                            st.session_state.page_number -= 1
                            st.rerun()

                with p_col2:
                    st.write(f"頁數: {st.session_state.page_number + 1} / {total_pages}")

                with p_col3:
                    if st.session_state.page_number < total_pages - 1:
                        if st.button("下一頁 ➡️"):
                            st.session_state.page_number += 1
                            st.rerun()
    else:
        st.write(f"找不到包含 '{selected_skill_lookup}' 技能的職缺。")


st.divider()
st.subheader("城市薪資分析")

# --- 城市與分類薪資比較 ---
# Find all categories with a reasonable number of jobs (e.g., >= 5) to provide a complete list
all_cat_counts = df_filtered['category_name'].dropna().value_counts()
available_categories_for_comparison = all_cat_counts[all_cat_counts >= 5].index.tolist()


# Add filters for city and category
selected_cities_for_comparison = st.multiselect(
    "選擇要比較的城市",
    options=sorted([city for city in df_filtered['city'].unique() if pd.notna(city)]),
    default=['臺北市', '高雄市']
)

# Set default categories for comparison, ensuring they exist in the options
default_categories_to_select = ['前端工程師', '後端工程師', '雲端工程師', '資料工程師']
default_categories = [cat for cat in default_categories_to_select if cat in available_categories_for_comparison]
# If none of the preferred defaults are available, fall back to the top one from the available list
if not default_categories and available_categories_for_comparison:
    default_categories = available_categories_for_comparison[:1]

selected_categories_for_comparison = st.multiselect(
    "選擇要比較的職缺分類",
    options=available_categories_for_comparison,
    default=default_categories
)

if selected_cities_for_comparison and selected_categories_for_comparison:
    comparison_df = df_filtered[
        df_filtered['city'].isin(selected_cities_for_comparison) &
        df_filtered['category_name'].isin(selected_categories_for_comparison)
    ].copy()

    # Filter out unreasonable salaries
    comparison_df = comparison_df[comparison_df['monthly_salary'] < MAX_REASONABLE_SALARY]
    comparison_df = comparison_df.dropna(subset=['monthly_salary'])

    if not comparison_df.empty:
        # 改為計算薪資中位數，以提供更穩健、更具代表性的比較
        comparison_median_salary = comparison_df.groupby(['city', 'category_name'])['monthly_salary'].median().round(0).reset_index()

        fig_comparison = px.bar(
            comparison_median_salary,
            x='category_name',
            y='monthly_salary',
            color='city',
            barmode='group',
            # title='城市與分類薪資比較',
            labels={'category_name': '職缺分類', 'monthly_salary': '薪資中位數 (元)', 'city': '城市'},
            text='monthly_salary'
        )
        fig_comparison.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        fig_comparison.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_comparison, use_container_width=True)
    else:
        st.write("無足夠資料可進行比較分析。")
else:
    st.write("請至少選擇一個城市和一個職缺分類進行比較。")
