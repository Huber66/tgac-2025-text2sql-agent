import json
import os
import pymysql
from decimal import Decimal
from datetime import datetime, date
from typing import List, Dict, Union

# 导入配置
import config

# ==========================================
# 第一部分：数据库连接工具 (原 db_utils.py)
# ==========================================

def get_db_connection():
    """
    创建并返回一个新的 pymysql 数据库连接。
    """
    try:
        # 使用 config.py 中的配置
        conn = pymysql.connect(**config.db_config)
        return conn
    except pymysql.Error as e:
        print(f"数据库连接失败: {e}")
        return None

def test_connection():
    """
    测试数据库连接并执行一个简单的查询。
    """
    print("正在尝试连接到数据库...")
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES;")
                tables = cursor.fetchall()
                print(f"数据库连接成功！在 '{config.db_config.get('database')}' 中找到 {len(tables)} 张表。")
                print("测试通过。")
                return True
        except pymysql.Error as e:
            print(f"数据库查询失败: {e}")
            return False
        finally:
            conn.close()
    else:
        print("测试失败：无法建立连接。")
        return False


# ==========================================
# 第二部分：结果格式化与执行工具 (原 agent_tools.py)
# ==========================================

class DecimalEncoder(json.JSONEncoder):
    """
    自定义 JSON 编码器，用于处理 Decimal、datetime、date 类型。
    (复用自官方 sql_exe.py 的核心逻辑)
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            # 保持与官方指南一致的逻辑:
            # 如果是整数(3.0)转int，否则保留两位小数(3.33)
            return float(obj) if obj != obj.to_integral_value() else int(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

def _normalize_numbers_in_result(result_list: List[Dict]) -> List[Dict]:
    """
    对查询结果中的数字进行标准化处理。
    这是比赛指南中的关键要求，用于确保 Agent 看到的数字格式与官方评测一致。
    """

    def _normalize_value(value):
        # 严格遵循指南：3.0 -> 3 (int), 3.3333 -> 3.33 (float, round 2)
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            else:
                return round(value, 2)
        # Decimal 类型在 StarRocks 中很常见，按指南要求处理
        if isinstance(value, Decimal):
            if value == value.to_integral_value():
                return int(value)
            else:
                # 保留两位小数
                return round(float(value), 2)
        else:
            return value

    normalized = [
        {key: _normalize_value(value) for key, value in row.items()}
        for row in result_list
    ]
    return normalized

class SqlExecutorTool:
    """
    一个封装了日志记录、SQL执行和结果格式化的类。
    主脚本将为每个问题创建一个此类的实例。
    """

    def __init__(self, log_dir: str):
        """
        初始化时，必须提供一个唯一的日志目录。

        Args:
            log_dir (str): 此工具所有日志的输出目录
                         (例如 "output/api_langgraph_runs/sql_30_...")
        """
        self.log_dir = log_dir
        self.step_count = 1
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_dir, "agent_tool_log.txt")
        # self._log(f"SqlExecutorTool 初始化，日志将写入: {self.log_dir}")

    def _log(self, message: str):
        """向主日志文件追加日志。"""
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] {message}\n")
        # print(message) # 可选：在控制台打印

    def run(self, sql_query: str) -> str:
        """
        Agent 将调用的主函数。
        它执行 SQL，记录所有内容，并返回一个字符串结果。

        Args:
            sql_query (str): Agent 生成的 SQL 语句。

        Returns:
            str: 格式化后的 JSON 结果字符串，或错误信息字符串。
        """
        step_prefix = f"step_{self.step_count:02d}"
        self._log(f"--- {step_prefix}: 接收到 SQL 执行任务 ---")
        self._log(f"传入的 SQL:\n{sql_query}")

        # 1. 将 Agent 生成的 SQL 语句保存到文件
        sql_file_path = os.path.join(self.log_dir, f"{step_prefix}_generated.sql")
        with open(sql_file_path, 'w', encoding='utf-8') as f:
            f.write(sql_query)

        conn = None
        try:
            # 2. 获取数据库连接 (直接调用本文件中的函数)
            conn = get_db_connection()
            if not conn:
                self._log("错误: 无法获取数据库连接。")
                return "Error: 无法获取数据库连接，请检查网络或配置。"

            self._log("数据库连接成功，正在执行查询...")

            # 3. 执行查询
            # 关键：使用 DictCursor 以便按列名处理
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(sql_query)
                query_result = cursor.fetchall()

            self._log(f"查询成功，获取到 {len(query_result)} 行原始数据。")

            # 4. 严格按照比赛要求格式化结果
            normalized_result = _normalize_numbers_in_result(query_result)
            self._log("数据已根据比赛规则进行格式化 (处理小数)。")

            # 5. 将格式化后的 JSON 结果保存到文件
            result_file_path = os.path.join(self.log_dir, f"{step_prefix}_result.json")
            with open(result_file_path, 'w', encoding='utf-8') as f:
                # 使用 DecimalEncoder 确保 json.dump 成功
                json.dump(normalized_result, f, ensure_ascii=False, indent=4, cls=DecimalEncoder)

            # 6. 将结果序列化为字符串，返回给 Agent
            # Agent 的 "Observation" 只能接收字符串
            return_str = json.dumps(normalized_result, ensure_ascii=False, cls=DecimalEncoder)
            self._log(f"执行成功。")

            return return_str

        except pymysql.Error as e:
            # 7. 处理 SQL 执行错误
            error_message = f"SQL 执行失败: {e}"
            self._log(f"!!! {error_message}")

            # 将错误信息保存到文件
            error_file_path = os.path.join(self.log_dir, f"{step_prefix}_error.txt")
            with open(error_file_path, 'w', encoding='utf-8') as f:
                f.write(error_message)

            # 将错误信息字符串返回给 Agent，触发它的“修正”
            return f"Error: {error_message}"

        finally:
            # 8. 清理
            if conn:
                conn.close()
            self.step_count += 1 # 为下一次调用（可能是修正）做准备

if __name__ == "__main__":
    # 当我们运行 !python execution_tools.py 时，测试数据库连接
    raise SystemExit(0 if test_connection() else 1)
