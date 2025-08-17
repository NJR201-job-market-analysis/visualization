import os
from pathlib import Path
from dotenv import load_dotenv

# 載入 .env 文件
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ 載入 .env 文件: {env_file}")
else:
    print(f"⚠️ .env 文件不存在: {env_file}")


MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_ACCOUNT = os.environ.get("MYSQL_ACCOUNT", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "mydb")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "job_market")
