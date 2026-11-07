"""Check local assets, dependencies and database without generating model output."""
import importlib
import json
import sys
from pathlib import Path


def main():
    failed = False
    print(f'Python: {sys.version.split()[0]} ({sys.executable})')
    for name in ('dotenv', 'pymysql', 'langchain_core', 'langchain_openai', 'langgraph'):
        try:
            importlib.import_module(name)
            print(f'[OK] import {name}')
        except ImportError as exc:
            print(f'[FAIL] import {name}: {exc}')
            failed = True
    if failed:
        return 1
    import config
    print(f'Profile: {config.PROFILE}; database: {config.db_config["database"]}')
    from execution_tools import test_connection
    for name in ('SCHEMA_PATH', 'KNOWLEDGE_PATH', 'DATASET_PATH', 'INSERT_SQL_PATH', 'CREATE_TABLE_PATH'):
        path = Path(getattr(config, name))
        exists = path.is_file()
        print(f'[{"OK" if exists else "FAIL"}] {name}: {path}')
        failed |= not exists
    if Path(config.DATASET_PATH).is_file():
        tasks = json.loads(Path(config.DATASET_PATH).read_text(encoding='utf-8'))
        print(f'Tasks: {len(tasks)}; golden: {sum(bool(t.get("golden_sql")) for t in tasks)}')
    print(f'DeepSeek API key: {"configured" if config.DEEPSEEK_API_KEY else "missing (cached mode still works)"}')
    failed |= not test_connection()
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
