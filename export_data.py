import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

# --- 設定 ---
OUTPUT_FILE_PATH = "jobs_data.parquet"

# --- 載入環境變數 ---
load_dotenv()
print("正在讀取 .env 檔案中的資料庫設定...")

# --- 建立資料庫連線 ---
def connect_db():
    user = os.getenv("MYSQL_ACCOUNT")
    password = os.getenv("MYSQL_PASSWORD")
    host = os.getenv("MYSQL_HOST")
    port = os.getenv("MYSQL_PORT")
    db = os.getenv("MYSQL_DATABASE")

    if not all([user, password, host, port, db]):
        raise ValueError("資料庫連線資訊不完整，請檢查您的 .env 檔案。")

    conn_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(conn_str)
    print("資料庫連線成功！")
    return engine

# --- 執行資料查詢 ---
def fetch_data(engine):
    query = """
    WITH FirstCategory AS (
        SELECT
            jc.job_id,
            MIN(c.name) AS category_name
        FROM jobs_categories jc
        LEFT JOIN categories c ON jc.category_id = c.id
        GROUP BY jc.job_id
    )
    SELECT
        j.*,
        GROUP_CONCAT(s.name SEPARATOR ',') AS aggregated_skills,
        COALESCE(fc.category_name, '未分類') AS category_name
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
    print("正在從資料庫查詢資料...")
    with engine.connect() as connection:
        df = pd.read_sql(query, connection)
    print(f"查詢完成！共擷取 {len(df)} 筆資料。")
    return df

# --- 主程式 ---
if __name__ == "__main__":
    try:
        db_engine = connect_db()
        jobs_df = fetch_data(db_engine)
        
        # --- 儲存為 Parquet 檔案 ---
        print(f"正在將資料儲存至 {OUTPUT_FILE_PATH}...")
        jobs_df.to_parquet(OUTPUT_FILE_PATH, index=False)
        print("="*50)
        print(f"✅ 資料匯出成功！")
        print(f"檔案已儲存於: {os.path.abspath(OUTPUT_FILE_PATH)}")
        print("您現在可以將 jobs_data.parquet 與您的專案一起上傳至 GitHub。")
        print("="*50)

    except Exception as e:
        print(f"❌ 發生錯誤：{e}")
