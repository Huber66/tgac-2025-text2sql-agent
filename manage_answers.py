import json
import os
import argparse
import sys
import config
from typing import List, Dict, Any, Optional, Tuple, Set

# --- 配置路径 (假设脚本在 code/ 目录下运行) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. 答案库 (Correct)
ANSWER_KEY_FILE = config.ANSWER_KEY_FILE
# 2. 错误样本库 (Error)
ERROR_SAMPLES_FILE = config.ERROR_SAMPLES_FILE
# 3. 结果文件
DEFAULT_RESULT_FILE = os.path.join(config.OUTPUT_DIR, "dataset_exe_result.json")
# 4. 原始题目
DATASET_PATH = config.DATASET_PATH


def canonicalize_result_v4(result_list: Optional[List[Dict]]) -> Optional[Tuple]:
    """将 result 列表转换为可哈希、可对比的“仅值”元组 (忽略列名, 忽略行序)"""
    if not isinstance(result_list, list): return None
    canonical_rows = []
    try:
        for row in result_list:
            if not isinstance(row, dict): continue
            values = list(row.values())
            str_values = [str(v) for v in values]
            canonical_rows.append(tuple(str_values))
        canonical_rows.sort()
        return tuple(canonical_rows)
    except Exception:
        return None

def load_json(filepath: str) -> Any:
    if not os.path.exists(filepath): return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"!!! 读取 {filepath} 失败: {e}")
        return []

def save_json(data: Any, filepath: str):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"已保存至: {filepath}")
    except Exception as e:
        print(f"!!! 保存失败: {e}")

def get_natural_key(item):
    try:
        return int(item.get('sql_id', '0').split('_')[1])
    except: return 0

def import_error_samples(target_ids: List[str], source_file: str):
    """功能 1: 导入新的错误到 error_samples.json"""
    print(f"--- [模式] 导入错误样本 (从 {source_file}) ---")

    source_data = load_json(source_file)
    source_map = {item['sql_id']: item for item in source_data if 'sql_id' in item}

    error_data = load_json(ERROR_SAMPLES_FILE)
    error_map = {item['sql_id']: item for item in error_data}

    count = 0
    for sql_id in target_ids:
        if sql_id not in source_map:
            print(f"  {sql_id}: 源文件中未找到结果，跳过。")
            continue

        res_item = source_map[sql_id]
        new_result = res_item.get('result')
        new_sql = res_item.get('sql') or res_item.get('query')

        new_canon = canonicalize_result_v4(new_result)
        if new_canon is None:
            print(f"  {sql_id}: 结果格式无效 (空或非列表)，跳过。")
            continue

        if sql_id not in error_map:
            error_map[sql_id] = {"sql_id": sql_id, "status": "error", "samples": []}

        existing_samples = error_map[sql_id]["samples"]
        is_exist = False
        for s in existing_samples:
            if canonicalize_result_v4(s.get('result')) == new_canon:
                is_exist = True
                break

        if not is_exist:
            existing_samples.append({"query": new_sql, "result": new_result})
            print(f"{sql_id}: 添加新错误样本 (当前共 {len(existing_samples)} 个)")
            count += 1
        else:
            print(f"ok {sql_id}: 该错误结果已存在，跳过。")

    if count > 0:
        sorted_list = sorted(error_map.values(), key=get_natural_key)
        save_json(sorted_list, ERROR_SAMPLES_FILE)
    else:
        print("--- 没有新的错误样本需要保存 ---")


def upsert_correct_answer(target_ids: List[str], source_file: str):
    """功能 2: 更新和插入 answer_key.json"""
    print(f"--- [模式] 录入正确答案 (从 {source_file}) ---")

    source_data = load_json(source_file)
    source_map = {item['sql_id']: item for item in source_data if 'sql_id' in item}

    key_data = load_json(ANSWER_KEY_FILE)
    key_map = {item['sql_id']: item for item in key_data}

    count = 0
    for sql_id in target_ids:
        if sql_id not in source_map:
            print(f"  {sql_id}: 源文件中未找到，跳过。")
            continue

        item = source_map[sql_id]
        key_map[sql_id] = {
            "sql_id": sql_id,
            "status": "correct",
            "query": item.get('sql') or item.get('query'),
            "result": item.get('result')
        }
        print(f"{sql_id}: 已更新为正确答案。")
        count += 1

    if count > 0:
        sorted_list = sorted(key_map.values(), key=get_natural_key)
        save_json(sorted_list, ANSWER_KEY_FILE)
    else:
        print("--- 没有数据更新 ---")


def show_status():
    """功能 3: 查看目前的正确题目和未正确题目 (排除 Golden SQL)"""
    print(f"--- [模式] 查看进度状态 ---")

    if not os.path.exists(DATASET_PATH):
        print(f"找不到数据集文件 {DATASET_PATH}，无法计算总进度。")
        all_ids = set()
        golden_ids = set()
    else:
        dataset = load_json(DATASET_PATH)
        all_ids = {item['sql_id'] for item in dataset}
        golden_ids = {item['sql_id'] for item in dataset if item.get('golden_sql')}

    key_data = load_json(ANSWER_KEY_FILE)
    my_correct_ids = {item['sql_id'] for item in key_data if item.get('status') == 'correct'}

    solved_ids = my_correct_ids.union(golden_ids)

    unsolved_ids = sorted(list(all_ids - solved_ids), key=lambda x: int(x.split('_')[1]) if '_' in x else 0)

    print(f"\n总题数: {len(all_ids)}")
    print(f"正确: {len(my_correct_ids)}")

    print(f"\n未解决: {len(unsolved_ids)}")

    print("\n--- 未解决列表 (Target List) ---")
    # 每行打印 10 个
    for i, uid in enumerate(unsolved_ids):
        print(f"{uid:<8}", end=" " if (i+1) % 10 != 0 else "\n")
    print("\n")

def compare_and_test(result_file: str):
    """功能 4: 测试 dataset_exe_result.json 对比 answer_key 和 error_samples"""
    print(f"--- [模式] 对比测试 (源: {result_file}) ---")

    result_data = load_json(result_file)
    if not result_data:
        print("源文件为空或不存在。")
        return

    # 加载基准
    correct_data = load_json(ANSWER_KEY_FILE)
    correct_map = {item['sql_id']: canonicalize_result_v4(item['result']) for item in correct_data if item.get('status') == 'correct'}

    error_data = load_json(ERROR_SAMPLES_FILE)
    # error_map: sql_id -> set of canonical results
    error_map = {}
    for item in error_data:
        sid = item['sql_id']
        if sid not in error_map: error_map[sid] = set()
        for s in item.get('samples', []):
            canon = canonicalize_result_v4(s.get('result'))
            if canon: error_map[sid].add(canon)

    print(f"{'SQL_ID':<10} | {'状态':<10} | 说明")
    print("-" * 50)

    stats = {"correct": 0, "known_error": 0, "unknown_error": 0, "no_record": 0}

    for item in result_data:
        sql_id = item.get('sql_id')
        current_res = canonicalize_result_v4(item.get('result'))

        status_str = ""
        desc = ""

        if sql_id in correct_map:
            if current_res == correct_map[sql_id]:
                status_str = "正确"
                desc = "与正确样本一致"
                stats["correct"] += 1
            else:
                if sql_id in error_map and current_res in error_map[sql_id]:
                    status_str = "错误"
                    desc = "与错误样本一致 (已知坑点)"
                    stats["known_error"] += 1
                else:
                    status_str = "未知"
                    desc = "与正确答案不一致，且未在错误库中发现"
                    stats["unknown_error"] += 1
        else:
            if sql_id in error_map and current_res in error_map[sql_id]:
                status_str = "XXX错误"
                desc = "与错误样本一致"
                stats["known_error"] += 1
            else:
                status_str = "无记录"
                desc = "没有该ID的正确记录，也未匹配到错误样本"
                stats["no_record"] += 1

        print(f"{sql_id:<10} | {status_str:<8} | {desc}")

    print("-" * 50)
    print(f"统计: 正确 {stats['correct']} | 已知错误 {stats['known_error']} | 新错误 {stats['unknown_error']} | 无记录 {stats['no_record']}")


def main():
    parser = argparse.ArgumentParser(description="答案库管理工具")
    subparsers = parser.add_subparsers(dest='command', help='可用指令')

    # 指令 1: 导入错误
    parser_err = subparsers.add_parser('import_error', help='导入新的错误样本')
    parser_err.add_argument('--ids', type=str, required=True, help='逗号分隔的 sql_id (e.g. sql_1,sql_2)')
    parser_err.add_argument('--file', type=str, default=DEFAULT_RESULT_FILE, help='结果源文件')

    # 指令 2: 录入正确
    parser_corr = subparsers.add_parser('add_correct', help='更新或插入正确答案')
    parser_corr.add_argument('--ids', type=str, required=True, help='逗号分隔的 sql_id')
    parser_corr.add_argument('--file', type=str, default=DEFAULT_RESULT_FILE, help='结果源文件')

    # 指令 3: 查看状态
    parser_status = subparsers.add_parser('status', help='查看当前的正确题目和未正确题目')

    # 指令 4: 对比测试
    parser_test = subparsers.add_parser('test', help='测试结果文件对比 AnswerKey 和 ErrorSamples')
    parser_test.add_argument('--file', type=str, default=DEFAULT_RESULT_FILE, help='要测试的结果文件')

    args = parser.parse_args()

    if args.command == 'import_error':
        ids = [i.strip() for i in args.ids.split(',')]
        import_error_samples(ids, args.file)
    elif args.command == 'add_correct':
        ids = [i.strip() for i in args.ids.split(',')]
        upsert_correct_answer(ids, args.file)
    elif args.command == 'status':
        show_status()
    elif args.command == 'test':
        compare_and_test(args.file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
