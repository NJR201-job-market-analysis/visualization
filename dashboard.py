import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
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


load_dotenv()


# --- 建立資料庫連線 ---
@st.cache_resource
def connect_db():
    user = os.getenv("MYSQL_ACCOUNT")
    password = os.getenv("MYSQL_PASSWORD")
    host = os.getenv("MYSQL_HOST")
    port = os.getenv("MYSQL_PORT")
    db = os.getenv("MYSQL_DATABASE")

    conn_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(conn_str)
    return engine


# --- 載入資料並預處理 ---
@st.cache_data
def load_data(_engine):
    query = """
    WITH FirstCategory AS (
        SELECT
            jc.job_id,
            MIN(c.name) AS category_name
        FROM jobs_categories jc
        JOIN categories c ON jc.category_id = c.id
        GROUP BY jc.job_id
    )
    SELECT
        j.*,
        GROUP_CONCAT(s.name SEPARATOR ',') AS aggregated_skills,
        fc.category_name
    FROM
        jobs AS j
    LEFT JOIN
        jobs_skills AS js ON j.id = js.job_id
    LEFT JOIN
        skills AS s ON js.skill_id = s.id
    LEFT JOIN
        FirstCategory AS fc ON j.id = fc.job_id
    GROUP BY
        j.id
    """
    with _engine.connect() as connection:
        df = pd.read_sql(query, connection)

    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    # 薪資標準化
    def normalize_salary(row):
        salary_min = row["salary_min"]
        salary_type = row["salary_type"]
        if pd.isna(salary_min):
            return None
        if salary_type == "年薪":
            return salary_min / 12
        elif salary_type == "日薪":
            return salary_min * 22
        elif salary_type == "時薪":
            return salary_min * 176
        return salary_min

    df["monthly_salary"] = df.apply(normalize_salary, axis=1)
    
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
st.title("📊 就業市場總覽")

engine = connect_db()
df = load_data(engine)

# --- Sidebar Filters ---
st.sidebar.header("篩選器")
selected_platform = st.sidebar.multiselect(
    "平台",
    options=df["platform"].unique(),
    default=df["platform"].unique(),
)
selected_city = st.sidebar.multiselect(
    "城市",
    options=df["city"].unique(),
    default=df["city"].unique(),
)
df_filtered = df[
    df["platform"].isin(selected_platform) & df["city"].isin(selected_city)
]

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
median_salary = salary_df_for_median['monthly_salary'].median() if not salary_df_for_median.empty else 0
col3.metric("💵 薪資中位數 (月)", f"{median_salary:,.0f} 元")

# 4. Median Experience Requirement
exp_df_for_median = df_filtered.copy()
exp_df_for_median['experience_min'] = pd.to_numeric(exp_df_for_median['experience_min'], errors='coerce')
exp_df_for_median = exp_df_for_median.dropna(subset=['experience_min'])
median_exp = exp_df_for_median['experience_min'].median() if not exp_df_for_median.empty else 0
col4.metric("📈 經驗要求中位數 (年)", f"{median_exp:.1f} 年")


st.divider()

# --- Market Overview ---
st.subheader("📊 市場總覽")

c1, c2 = st.columns(2)

with c1:
    # 1. Job count per platform
    platform_df = df_filtered["platform"].value_counts().reset_index()
    platform_df.columns = ["platform", "count"]
    fig_platform = px.bar(
        platform_df, 
        y="count", 
        x="platform", 
        title="各平台職缺數量",
        labels={'platform': '平台', 'count': '職缺數'},
        text='count'
    )
    fig_platform.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig_platform.update_layout(xaxis={'categoryorder':'total descending'})
    st.plotly_chart(fig_platform, use_container_width=True)

with c2:
    # 2. Job count per city (top 10)
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
    # 3. Job heat (most frequent job categories)
    category_df = df_filtered['category_name'].dropna().value_counts().nlargest(10).reset_index()
    category_df.columns = ['category', 'count']
    fig_category_heat = px.bar(
        category_df,
        y='count',
        x='category',
        title='職缺熱度 (Top 10 分類)',
        labels={'category': '職缺分類', 'count': '職缺數'},
        text='count'
    )
    fig_category_heat.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    fig_category_heat.update_layout(xaxis={'categoryorder':'total descending'}, xaxis_tickangle=-45)
    st.plotly_chart(fig_category_heat, use_container_width=True)

with c4:
    # 4. Work experience requirement distribution
    def map_experience(exp):
        try:
            if pd.isna(exp):
                return '無需經驗 / 不拘'
            exp_num = int(exp)
            if exp_num <= 0:
                return '無需經驗 / 不拘'
            elif exp_num <= 3:
                return '1-3年'
            elif exp_num <= 5:
                return '3-5年'
            else:
                return '5年以上'
        except (ValueError, TypeError):
            return '無需經驗 / 不拘'

    exp_df = df_filtered.copy()
    exp_df['experience_group'] = exp_df['experience_min'].apply(map_experience)
    exp_dist = exp_df['experience_group'].value_counts().reset_index()
    exp_dist.columns = ['group', 'count']
    
    # Define a logical order for the chart
    order = ['無需經驗 / 不拘', '1-3年', '3-5年', '5年以上']

    fig_exp_dist = px.bar(
        exp_dist,
        x='group',
        y='count',
        title='工作經驗要求分佈',
        labels={'group': '經驗要求', 'count': '職缺數'},
        text='count',
        category_orders={'group': order}
    )
    fig_exp_dist.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    st.plotly_chart(fig_exp_dist, use_container_width=True)


# --- Skill Analysis ---
st.divider()
st.subheader("🧠 技能分析 (依職缺分類)")

# Add a selectbox to filter by category
top_categories = df_filtered['category_name'].dropna().value_counts().nlargest(10).index.tolist()
selected_category = st.selectbox(
    "選擇職缺分類來查看技能需求",
    options=top_categories
)

if selected_category:
    # Filter dataframe by the selected category
    category_df = df_filtered[df_filtered['category_name'] == selected_category]

    c3, c4 = st.columns(2)
    with c3:
        # --- Popular Skills Treemap ---
        skills_flat = category_df["required_skills"].dropna().str.cat(sep=",").split(",")
        skill_counts = Counter([s.strip() for s in skills_flat if s.strip()])
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
                skills = [s.strip() for s in row['required_skills'].split(',')]
                for skill in skills:
                    skills_list.append({'skill': skill, 'monthly_salary': row['monthly_salary']})
        
        if skills_list:
            skills_exploded_df = pd.DataFrame(skills_list)
            skill_analysis = skills_exploded_df.groupby('skill')['monthly_salary'].agg(['mean', 'count']).reset_index()
            skill_analysis = skill_analysis.rename(columns={'mean': 'avg_salary'})

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

# --- Skill Reverse Lookup ---
st.subheader("🔍 探索技能的職務應用 (依技能反查)")
# Create a list of top skills for the selectbox
all_skills_flat = df_filtered["required_skills"].dropna().str.cat(sep=",").split(",")
all_skill_counts = Counter([s.strip() for s in all_skills_flat if s.strip()])
top_50_skills = [skill for skill, count in all_skill_counts.most_common(50)]

selected_skill_lookup = st.selectbox(
    "選擇一個技能來查詢相關職缺分類與範例",
    options=sorted(top_50_skills)
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
            st.markdown(f"##### '{selected_skill_lookup}' 主要應用於以下職類")
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
st.subheader("🏙️ 分類與城市分析")

# --- 城市與分類薪資比較 ---
# Find top 10 most common categories to populate the filter
top_10_common_categories = df_filtered['category_name'].dropna().value_counts().nlargest(10).index.tolist()

# Add filters for city and category
selected_cities_for_comparison = st.multiselect(
    "選擇要比較的城市",
    options=sorted([city for city in df_filtered['city'].unique() if pd.notna(city)]),
    default=df_filtered['city'].value_counts().nlargest(2).index.tolist() # Default to top 2 cities
)

selected_categories_for_comparison = st.multiselect(
    "選擇要比較的職缺分類",
    options=top_10_common_categories,
    default=top_10_common_categories[:3] # Default to top 3 most common categories
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
        # Calculate average salary
        comparison_avg_salary = comparison_df.groupby(['city', 'category_name'])['monthly_salary'].mean().round(0).reset_index()

        fig_comparison = px.bar(
            comparison_avg_salary,
            x='category_name',
            y='monthly_salary',
            color='city',
            barmode='group',
            title='城市與分類薪資比較',
            labels={'category_name': '職缺分類', 'monthly_salary': '平均月薪', 'city': '城市'},
            text='monthly_salary'
        )
        fig_comparison.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        fig_comparison.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_comparison, use_container_width=True)
    else:
        st.write("無足夠資料可進行比較分析。")
else:
    st.write("請至少選擇一個城市和一個職缺分類進行比較。")


# --- 城市職缺分類 ---
top_cities = df_filtered['city'].value_counts().nlargest(5).index
city_category_df = df_filtered[df_filtered['city'].isin(top_cities)]
city_category_summary = city_category_df.groupby(['city', 'category_name']).size().reset_index(name='count')

# Calculate percentage
city_sums = city_category_summary.groupby('city')['count'].transform('sum')
city_category_summary['percentage'] = 100 * city_category_summary['count'] / city_sums

fig_city_category = px.bar(
    city_category_summary,
    x='city',
    y='percentage',
    color='category_name',
    title='熱門城市職缺分類佔比',
    labels={'city': '城市', 'percentage': '職缺佔比 (%)', 'category_name': '職缺分類'},
    barmode='stack'
)
st.plotly_chart(fig_city_category, use_container_width=True)

# --- 城市薪資範圍比較 ---
st.markdown("##### 🏙️ 熱門城市薪資範圍比較")
city_salary_df = df_filtered[df_filtered['city'].isin(top_cities)].copy()
city_salary_df = city_salary_df.dropna(subset=['monthly_salary'])
city_salary_df = city_salary_df[city_salary_df['monthly_salary'] < MAX_REASONABLE_SALARY]

if not city_salary_df.empty:
    # Calculate quantiles
    salary_quantiles = city_salary_df.groupby('city')['monthly_salary'].quantile([0.25, 0.5, 0.75]).unstack().reset_index()
    salary_quantiles.columns = ['city', '低標 (25%)', '中位數 (50%)', '高標 (75%)']
    
    # Melt the dataframe for plotting
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
        title='熱門城市薪資範圍比較',
        labels={'city': '城市', '月薪': '月薪 (元)'},
        text='月薪'
    )
    fig_city_salary_range.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
    st.plotly_chart(fig_city_salary_range, use_container_width=True)
else:
    st.write("無足夠資料可進行城市薪資分析。")


st.divider()
st.subheader("📊 市場排行榜")

# --- First Row of Leaderboards ---
insight_col1, insight_col2 = st.columns(2)

with insight_col1:
    # 1. Top Hirers
    st.markdown("##### 🏢 主要招聘公司")
    top_hirers = df_filtered['company_name'].dropna().value_counts().nlargest(10).reset_index()
    top_hirers.columns = ['company', 'count']
    fig_hirers = px.bar(
        top_hirers,
        x='count',
        y='company',
        orientation='h',
        title="Top 10 招聘公司",
        labels={'company': '公司', 'count': '職缺數'}
    )
    fig_hirers.update_layout(yaxis={'categoryorder':'total ascending'}, title_font_size=16, height=400)
    st.plotly_chart(fig_hirers, use_container_width=True)

with insight_col2:
    # 2. Top Paying Categories
    st.markdown("##### 💵 高薪職缺分類排行")
    # Filter for categories with at least 5 job postings
    cat_counts = df_filtered['category_name'].value_counts()
    valid_categories = cat_counts[cat_counts >= 5].index
    
    high_paying_cat_df = df_filtered[df_filtered['category_name'].isin(valid_categories)].copy()
    high_paying_cat_df = high_paying_cat_df[high_paying_cat_df['monthly_salary'] < MAX_REASONABLE_SALARY]
    
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
    fig_top_cat.update_layout(title_font_size=16, height=400)
    st.plotly_chart(fig_top_cat, use_container_width=True)

# --- Second Row for the last chart ---
# 3. Top Paying Companies
st.markdown("##### 💰 高薪公司排行")
# Filter for companies with at least 5 job postings
comp_counts = df_filtered['company_name'].value_counts()
valid_companies = comp_counts[comp_counts >= 5].index

high_paying_comp_df = df_filtered[df_filtered['company_name'].isin(valid_companies)].copy()
high_paying_comp_df = high_paying_comp_df[high_paying_comp_df['monthly_salary'] < MAX_REASONABLE_SALARY]

top_paying_companies = high_paying_comp_df.groupby('company_name')['monthly_salary'].median().nlargest(10).reset_index()
top_paying_companies.columns = ['company', 'median_salary']

fig_top_comp = px.bar(
    top_paying_companies.sort_values('median_salary', ascending=True),
    x='median_salary',
    y='company',
    orientation='h',
    title="Top 10 高薪公司",
    labels={'company': '公司', 'median_salary': '薪資中位數 (元)'},
    text='median_salary'
)
fig_top_comp.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
fig_top_comp.update_layout(title_font_size=16, height=400)
st.plotly_chart(fig_top_comp, use_container_width=True)
