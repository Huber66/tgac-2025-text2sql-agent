import os
from dotenv import load_dotenv

#从.env文件加载变量
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_DIR, ".env"))

PROFILE = os.environ.get('TGAC_PROFILE', 'demo')
if PROFILE not in {'demo', 'competition'}:
    raise ValueError('TGAC_PROFILE must be demo or competition')
DATA_ROOT = os.environ.get('TGAC_DATA_DIR', os.path.join(PROJECT_DIR, 'data', PROFILE))
if not os.path.isabs(DATA_ROOT):
    DATA_ROOT = os.path.join(PROJECT_DIR, DATA_ROOT)

# Demo and competition profiles use different databases and local artifacts.
db_config = {
    'host': os.environ.get('DB_HOST', '127.0.0.1'),
    'port': int(os.environ.get('DB_PORT', '19030')),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'tgac_demo' if PROFILE == 'demo' else 'tgac_contest'),
    'charset': 'utf8mb4',
    'connect_timeout': 10,
    'read_timeout': 180,
    'write_timeout': 180,
}

#API
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")

BASE_DIR = DATA_ROOT
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output', PROFILE)
ANSWER_KEY_FILE = os.path.join(DATA_ROOT, 'answer_key.json')
ERROR_SAMPLES_FILE = os.path.join(DATA_ROOT, 'error_samples.json')
LOGIC_GUIDES_FILE = os.path.join(DATA_ROOT, 'logic_guides.json')

DATA_DIR = os.path.join(BASE_DIR, "data")
SQL_FILE_DIR = os.path.join(BASE_DIR, "sql_file")

#具体文件路径
SCHEMA_PATH = os.path.join(DATA_DIR, "schema.json")
KNOWLEDGE_PATH = os.path.join(DATA_DIR, "common_knowledge.md")
DATASET_PATH = os.path.join(DATA_DIR, "final_dataset.json")
INSERT_SQL_PATH = os.path.join(DATA_DIR, "insert_sql.json")

#SQL脚本路径
CREATE_TABLE_PATH = os.path.join(SQL_FILE_DIR, "create_table.sql")
DROP_TABLE_PATH = os.path.join(SQL_FILE_DIR, "drop_table.sql")
