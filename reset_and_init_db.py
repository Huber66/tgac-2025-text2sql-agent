import pymysql
import json
import os
import sys
import argparse

# 导入配置
import config

def get_raw_connection():
    conf = config.db_config.copy()
    if 'database' in conf:
        del conf['database']

    try:
        return pymysql.connect(**conf)
    except pymysql.Error as e:
        print(f"!!! 连接数据库服务失败: {e}")
        sys.exit(1)

def split_sql_statements(sql_content):
    """
    智能切分 SQL 语句，忽略引号内的分号。
    解决 COMMENT "A; B" 被错误切断的问题。
    """
    statements = []
    current_statement = []
    in_single_quote = False
    in_double_quote = False
    in_back_quote = False

    for char in sql_content:
        current_statement.append(char)

        if char == "'" and not in_double_quote and not in_back_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote and not in_back_quote:
            in_double_quote = not in_double_quote
        elif char == '`' and not in_single_quote and not in_double_quote:
            in_back_quote = not in_back_quote
        elif char == ';' and not in_single_quote and not in_double_quote and not in_back_quote:
            stmt = "".join(current_statement).strip()
            if stmt:
                statements.append(stmt)
            current_statement = []
    if current_statement:
        stmt = "".join(current_statement).strip()
        if stmt:
            statements.append(stmt)

    return statements

def reset_database(force=False):
    """第一步：删除旧库，创建新库"""
    db_name = config.db_config.get('database', 'contest_db')
    print(f"\n=== [Step 1] 正在重置数据库: {db_name} ===")

    conn = get_raw_connection()
    try:
        with conn.cursor() as cursor:
            safe_name = db_name.replace('`', '``')
            cursor.execute('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s', (db_name,))
            if cursor.fetchone()[0] and not force:
                raise RuntimeError('数据库已有表。为避免清空现有数据已停止；确需重置时增加 --force。')
            if force:
                print(f"-> 正在删除旧数据库 (如果存在)...")
                cursor.execute(f"DROP DATABASE IF EXISTS `{safe_name}`")

            print(f"-> 正在创建新数据库...")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{safe_name}`")
            print(f"-> 数据库 {db_name} 重置成功。")
    except Exception as e:
        print(f"!!! 重置数据库失败: {e}")
        sys.exit(1)
    finally:
        conn.close()

def create_tables():
    """第二步：执行建表语句 (使用智能切分)"""
    sql_file = config.CREATE_TABLE_PATH
    print(f"\n=== [Step 2] 正在创建表结构 (来自 {sql_file}) ===")

    if not os.path.exists(sql_file):
        raise FileNotFoundError(sql_file)

    conn = pymysql.connect(**config.db_config)
    try:
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        print("-> 正在解析 SQL 文件 (智能处理引号内的分号)...")
        statements = split_sql_statements(sql_content)
        print(f"-> 解析出 {len(statements)} 条建表语句。")

        count = 0
        fail_count = 0
        with conn.cursor() as cursor:
            for stmt in statements:
                if stmt.startswith('--') or stmt.startswith('/*'):
                    continue

                try:
                    cursor.execute(stmt)
                    count += 1
                except Exception as e:
                    fail_count += 1
                    print(f"!!! 建表失败: {stmt[:50]}...")
                    print(f"    错误: {e}")

        conn.commit()
        print(f"-> 建表完成。成功: {count}, 失败: {fail_count}")
        if fail_count > 0:
            raise RuntimeError(f'{fail_count} 张表创建失败，停止初始化。')

    except Exception as e:
        print(f"!!! 创建表过程发生错误: {e}")
        raise
    finally:
        conn.close()

def insert_all_data():
    """第三步：插入全量数据"""
    json_file = config.INSERT_SQL_PATH
    print(f"\n=== [Step 3] 正在插入全量数据 (来自 {json_file}) ===")

    if not os.path.exists(json_file):
        raise FileNotFoundError(json_file)

    conn = pymysql.connect(**config.db_config)
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        total = len(data)
        print(f"-> 共找到 {total} 条数据插入任务。")

        success_count = 0
        fail_count = 0

        batch_size = 50

        with conn.cursor() as cursor:
            for i, item in enumerate(data, 1):
                insert_sql = item.get('insert_sql')
                sql_id = item.get('sql_id', 'unknown')

                if insert_sql:
                    try:
                        cursor.execute(insert_sql)
                        success_count += 1
                    except Exception as e:
                        fail_count += 1
                        print(f"!!! ({sql_id}) 插入失败: {e}")

                if i % batch_size == 0:
                    conn.commit()
                    print(f"   进度: {i}/{total} ...")

            # 提交剩余的
            conn.commit()

        print(f"-> 数据插入完成。成功: {success_count}, 失败: {fail_count}")
        if fail_count:
            raise RuntimeError(f'{fail_count} 条插入任务失败。')

    except Exception as e:
        print(f"!!! 插入过程发生严重错误: {e}")
        raise
    finally:
        conn.close()

def run_init(force=False):
    """执行完整的初始化流程"""
    for path in (config.CREATE_TABLE_PATH, config.INSERT_SQL_PATH):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
    reset_database(force=force)
    create_tables()
    insert_all_data()
    print("\n=== ✅ 数据库环境全量初始化完成 ===")

def run_test():
    """仅测试连接"""
    print("\n=== 正在测试数据库连接 ===")
    try:
        conn = pymysql.connect(**config.db_config)
        with conn.cursor() as cursor:
            cursor.execute("SELECT DATABASE();")
            db_name = cursor.fetchone()[0]
            print(f"-> 连接成功！当前数据库: {db_name}")

            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            print(f"-> 表数量: {len(tables)}")

            print("-> 正在检查数据概况:")
            for table in tables[:86]:
                t_name = table[0]
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM `{t_name}`")
                    count = cursor.fetchone()[0]
                    print(f"   - {t_name}: {count} 行")
                except:
                    pass

        conn.close()
        print("=== ✅ 测试通过 ===")
        return True
    except Exception as e:
        print(f"!!! ❌ 连接测试失败: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据库重置与初始化工具")
    parser.add_argument('--mode', type=str, required=True, choices=['init', 'test'],
                        help="模式: 'init' (清空并重置数据库) 或 'test' (仅测试连接)")
    parser.add_argument('--force', action='store_true', help='允许删除已有数据库后重新初始化，会清空数据')

    # 适配 Jupyter 和 命令行
    if len(sys.argv) > 1 and (sys.argv[1] == '--mode' or sys.argv[1] in ['-h', '--help']):
         args = parser.parse_args()
         if args.mode == 'init':
             run_init(force=args.force)
         elif args.mode == 'test':
             raise SystemExit(0 if run_test() else 1)
    else:
        # 默认行为（如果直接运行但没参数，防止报错）
        print("请使用 --mode init 或 --mode test")
