import json
import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Any, Annotated, Optional, Tuple, Set
import operator
import re
import threading
import concurrent.futures
import time

#  第三方库导入
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import Tool, tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

#  本地模块导入
import config
try:
    from prompt_engine import SchemaRetriever, PromptBuilder
    from execution_tools import SqlExecutorTool, DecimalEncoder, test_connection
except ImportError as e:
    print(f"!!! 模块导入失败: {e}")
    sys.exit(1)


#全局配置与锁

DEEPSEEK_API_KEY = config.DEEPSEEK_API_KEY
DEEPSEEK_API_BASE = config.DEEPSEEK_API_BASE

#  路径配置
ANSWER_KEY_FILE = config.ANSWER_KEY_FILE
ERROR_SAMPLES_FILE = config.ERROR_SAMPLES_FILE
DATASET_PATH = config.DATASET_PATH

#  并发锁
FILE_LOCK = threading.Lock() # 文件写入锁
DB_LOCK = threading.Lock()   # 数据库执行锁 (防止死锁)


# 2. 辅助逻辑


def canonicalize_result_v4(result_list: Optional[List[Dict]]) -> Optional[Tuple]:
    """
    将 'result' 列表转换为可哈希、可对比的“仅值”元组。
    """
    if not isinstance(result_list, list):
        return None

    canonical_rows = []
    try:
        for row in result_list:
            if not isinstance(row, dict):
                continue
            # 提取所有值，转字符串，转元组
            values = list(row.values())
            str_values = [str(v) for v in values]
            canonical_rows.append(tuple(str_values))

        # 对行排序，忽略行序差异
        canonical_rows.sort()
        return tuple(canonical_rows)
    except Exception:
        return None

def load_deepseek_model(model_name: str = None) -> ChatOpenAI:
    if not DEEPSEEK_API_KEY:
        raise ValueError("错误: 未配置 DEEPSEEK_API_KEY。请检查 .env 文件。")

    final_model = model_name or config.DEEPSEEK_MODEL
    print(f" 正在加载 DeepSeek API 模型: {final_model} ")
    print(" 模式: 非思考模式，使用工具调用执行 SQL ")

    llm = ChatOpenAI(
        model=final_model,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_BASE,
        temperature=0.0,
        max_tokens=32768,
        timeout=120,
        max_retries=1,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return llm

def load_correct_answers(key_file: str) -> Dict[str, Dict[str, Any]]:
    correct_answers_map = {}
    if not os.path.exists(key_file):
        return correct_answers_map
    try:
        with open(key_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for item in data:
            if item.get("status") == "correct":
                sql_id = item.get("sql_id")
                if sql_id:
                    correct_answers_map[sql_id] = {
                        "query": item.get("query"),
                        "result": item.get("result")
                    }
        print(f" [AnswerCache] 成功加载 {len(correct_answers_map)} 条 [正确] 答案。 ")
        return correct_answers_map
    except Exception as e:
        print(f" [AnswerCache] 加载失败: {e} ")
        return {}

def load_error_result_blacklist(key_file: str) -> Dict[str, Set[Tuple]]:
    error_blacklist = {}
    if not os.path.exists(key_file):
        return error_blacklist
    try:
        with open(key_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        count = 0
        for item in data:
            # V38: error_samples.json 中的所有记录都视为错误
            sql_id = item.get("sql_id")
            samples = item.get("samples", [])

            if sql_id and samples:
                if sql_id not in error_blacklist:
                    error_blacklist[sql_id] = set()

                for s in samples:
                    raw_result = s.get("result")
                    canonical = canonicalize_result_v4(raw_result)
                    if canonical is not None:
                        error_blacklist[sql_id].add(canonical)
                        count += 1

        print(f" [ErrorBlacklist] 成功加载 {len(error_blacklist)} 个题目的 {count} 条错误结果样本。 ")
        return error_blacklist
    except Exception as e:
        print(f" [ErrorBlacklist] 加载失败: {e} ")
        return {}


# 3. 工具定义 (Tools) - 必须是全局函数


@tool
def submit_final_sql(final_sql_query: str) -> str:
    """
    (!!!) 仅在你 100% 确认 SQL 语法和逻辑都正确时，才调用此工具。
    这是你的最后一步，用于提交你的最终答案。
    此工具接收你最终的、完整的 SQL 查询字符串。
    你 *必须* 在调用此工具之前，已经用 `execute_sql_tool` 成功运行过这个 SQL。
    """
    return "Final SQL query has been successfully submitted."

@tool
def revise_plan(new_plan_description: str) -> str:
    """
    (!!!) 当你意识到你最初的“阶段 1 规划”存在逻辑错误时，调用此工具。
    这在“阶段 2：执行与修正”循环中非常重要。
    使用此工具来声明一个 *全新* 的、*修正后* 的规划。
    在调用此工具后，你的下一步“思考”应该围绕着执行这个 *新* 规划。
    """
    print(f" [Helper] Agent 正在修正其规划: {new_plan_description[:100]}... ")
    return "Your plan has been successfully revised. You must now follow this new plan."


# 4. 核心协调器 (LangGraphCoordinator)


class AgentState(TypedDict):
    original_input_prompt: str
    messages: Annotated[List[BaseMessage], operator.add]

class LangGraphCoordinator:

    def __init__(self,
                 llm_model: Any,
                 retriever: SchemaRetriever,
                 builder: PromptBuilder,
                 correct_answers_map: Dict,
                 error_result_blacklist: Dict):
        self.llm_model = llm_model
        self.retriever = retriever
        self.builder = builder
        self.correct_answers_map = correct_answers_map
        self.error_result_blacklist = error_result_blacklist
        self.validation_failure_counts = {}

    def _check_result_blacklist(self, sql_id: str, submitted_sql: str, messages: List[BaseMessage]) -> Tuple[str, str]:
        """检查结果是否在黑名单中"""
        if sql_id not in self.error_result_blacklist:
            return "PASS", ""

        # 这里我们需要为了拦截逻辑，去历史记录找结果
        # 注意：这只是为了拦截判断，和最终提取结果的逻辑是分开的

        def normalize_sql(s: str) -> str:
            return s.strip().rstrip(';') if isinstance(s, str) else ""

        target_norm_sql = normalize_sql(submitted_sql)
        found_result_json = None

        # 倒序查找最近一次执行结果
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, ToolMessage) and "Error:" not in str(msg.content):
                tool_call_id = msg.tool_call_id
                for j in range(i - 1, -1, -1):
                    prev = messages[j]
                    if isinstance(prev, AIMessage) and prev.tool_calls:
                        for tc in prev.tool_calls:
                            if tc['id'] == tool_call_id and tc['name'] == 'execute_sql_tool':
                                args = tc.get('args', {})
                                executed_sql = None
                                for k in ['sql_query', 'query', '__arg1']:
                                    if k in args: executed_sql = args[k]; break
                                if not executed_sql: executed_sql = list(args.values())[0] if args else ""

                                if normalize_sql(executed_sql) == target_norm_sql:
                                    try:
                                        found_result_json = json.loads(msg.content)
                                    except: pass
                            if found_result_json: break
                    if found_result_json: break
            if found_result_json: break

        # 如果拦截器找不到历史结果，说明 Agent 没跑过这个 SQL 或者格式变了
        # 在这种情况下，我们无法进行黑名单拦截，只能放行（或者强制打回要求跑一遍）
        # 为了不卡死，这里选择放行，但在最终提取时我们会强制重跑
        if found_result_json is None:
            return "PASS", "No execution history found, skipping blacklist check."

        current_canonical = canonicalize_result_v4(found_result_json)

        if current_canonical in self.error_result_blacklist[sql_id]:
            return "FAIL", "Error: (自动拦截) 你的执行结果与已知错误完全一致！"

        return "PASS", "Result check passed."

    def _save_minimal_log(self, sql_id: str, sql_str: str, log_dir: str):
        print(f" [AnswerCache] ({sql_id}) 创建最小日志... ")
        sql_file_path = os.path.join(log_dir, "_FINAL_ANSWER.sql")
        with open(sql_file_path, 'w', encoding='utf-8') as f:
            f.write(f"-- SQL loaded from answer_key.json --\n{sql_str}")

    def _get_submitted_sql(self, messages: List[BaseMessage]) -> Optional[str]:
        """从消息历史中提取最后一次 submit_final_sql 的参数"""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc['name'] == 'submit_final_sql':
                        return tc['args'].get('final_sql_query')
        return None

    def _build_graph(self, llm_with_tools: Any, tool_list: List[Tool], simple_log_file: str, sql_id: str):

        def call_model(state: AgentState):
            original_prompt = state['original_input_prompt']
            scratchpad_messages = state['messages']
            with open(simple_log_file, 'a', encoding='utf-8') as f:
                if scratchpad_messages:
                    f.write("\n\n [Agent 观察] \n")
                    f.write(str(scratchpad_messages[-1].content)[:2000] + "...\n")

            llm_input_messages = [
                HumanMessage(content=f""" 你的最高指示 (不可遗忘) \n{original_prompt}\n 最高指示结束 \n 以下是你当前的思考和行动历史 """)
            ]
            llm_input_messages.extend(scratchpad_messages)
            response = llm_with_tools.invoke(llm_input_messages)

            with open(simple_log_file, 'a', encoding='utf-8') as f:
                f.write("\n\n [Agent 思考] \n")
                f.write(response.content + "\n")
            return {"messages": [response]}

        action_tools = [t for t in tool_list if t.name != 'submit_final_sql']
        action_node = ToolNode(action_tools)

        def interceptor_node(state: AgentState) -> dict:
            last_message = state['messages'][-1]
            tool_call = last_message.tool_calls[0]
            args = tool_call.get('args', {})
            submitted_sql = args.get('final_sql_query')

            print(f" [Interceptor] 检查 {sql_id} ... ")
            current_fails = self.validation_failure_counts.get(sql_id, 0)
            status, message = self._check_result_blacklist(sql_id, submitted_sql, state['messages'])

            if status == "FAIL":
                current_fails += 1
                self.validation_failure_counts[sql_id] = current_fails
                if current_fails == 5:
                    print(f" [Interceptor] {sql_id} 5次失败。绝境模式触发。 ")
                    warning_msg = "Error: (系统强制干预) 连续5次错误！请尝试完全不同的思路。"
                    return {"messages": [ToolMessage(content=warning_msg, tool_call_id=tool_call['id'])]}
                elif current_fails > 5:
                    print(f" [Interceptor] {sql_id} 放弃拦截。 ")
                    return {"messages": [ToolMessage(content="Success: (强制通过) 已达重试上限。", tool_call_id=tool_call['id'])]}
                else:
                    print(f" [Interceptor] 拦截 (第{current_fails}次)。 ")
                    return {"messages": [ToolMessage(content=message, tool_call_id=tool_call['id'])]}
            else:
                print(f" [Interceptor] 通过。 ")
                self.validation_failure_counts[sql_id] = 0
                return {"messages": [ToolMessage(content="Success: 提交成功。", tool_call_id=tool_call['id'])]}

        def should_continue(state: AgentState):
            last_message = state['messages'][-1]
            if not last_message.tool_calls: return "end"
            if last_message.tool_calls[0]['name'] == 'submit_final_sql': return "interceptor"
            return "action"

        def after_interceptor(state: AgentState):
            last_message = state['messages'][-1]
            if "Success:" in str(last_message.content): return "end"
            return "agent"

        workflow = StateGraph(AgentState)
        workflow.add_node("agent", call_model)
        workflow.add_node("action", action_node)
        workflow.add_node("interceptor", interceptor_node)
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", should_continue, {"action": "action", "interceptor": "interceptor", "end": END})
        workflow.add_edge("action", "agent")
        workflow.add_conditional_edges("interceptor", after_interceptor, {"agent": "agent", "end": END})

        return workflow.compile()

    def run_task(self, task_data: Dict[str, Any], ignore_cache: bool = False, cache_only: bool = False) -> Optional[Dict[str, Any]]:
        """并发安全运行任务"""
        sql_id = task_data.get("sql_id", "unknown_task")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        if sql_id not in self.validation_failure_counts:
            self.validation_failure_counts[sql_id] = 0

        #  缓存执行 (带锁)
        if not ignore_cache and sql_id in self.correct_answers_map:
            print(f" [{sql_id}] 命中缓存，验证中... ")
            correct_entry = self.correct_answers_map[sql_id]
            sql_str = correct_entry.get("query")
            if sql_str:
                log_dir = os.path.join(config.OUTPUT_DIR, "api_langgraph_runs", sql_id, f"{sql_id}_{timestamp}_EXEC_FROM_KEY")
                os.makedirs(log_dir, exist_ok=True)
                cache_executor = SqlExecutorTool(log_dir=log_dir)
                try:
                    with DB_LOCK:
                        result_json_str = cache_executor.run(sql_str)
                    if not result_json_str.strip().startswith("Error"):
                        result_obj = json.loads(result_json_str)
                        self._save_minimal_log(sql_id, sql_str, log_dir)
                        return { "sql_id": sql_id, "sql": sql_str, "result": result_obj }
                except Exception: pass
        if cache_only or self.llm_model is None:
            print(f"!!! [{sql_id}] 缓存不存在或执行失败。")
            return None

        #  Agent 启动
        print(f" [{sql_id}] 启动 DeepSeek Agent... ")
        log_dir = os.path.join(config.OUTPUT_DIR, "api_langgraph_runs", sql_id, f"{sql_id}_{timestamp}")
        os.makedirs(log_dir, exist_ok=True)
        simple_log_path = os.path.join(log_dir, "thinking_process.log")
        with open(simple_log_path, 'w', encoding='utf-8') as f:
            f.write(f" {sql_id} 思考过程日志 \n")

        sql_tool_instance = SqlExecutorTool(log_dir=log_dir)
        def safe_sql_execute(query: str) -> str:
            with DB_LOCK:
                return sql_tool_instance.run(query)

        sql_exec_tool = Tool(
            name="execute_sql_tool",
            func=safe_sql_execute,
            description="执行 StarRocks SQL。"
        )

        tool_list = [sql_exec_tool, submit_final_sql, revise_plan]
        llm_with_tools = self.llm_model.bind_tools(tool_list)
        app = self._build_graph(llm_with_tools, tool_list, simple_log_file=simple_log_path, sql_id=sql_id)

        question = task_data.get("question")
        table_list = task_data.get("table_list")
        knowledge = task_data.get("knowledge", "")

        schema_text = self.retriever.get_relevant_schema_as_text(table_list)

        final_prompt = self.builder.build_agent_input(
            sql_id=sql_id,
            question=question,
            relevant_schema_string=schema_text,
            task_specific_knowledge=knowledge
        )

        with open(os.path.join(log_dir, "prompt.txt"), 'w', encoding='utf-8') as f:
            f.write(final_prompt)

        final_state = {"messages": []}
        try:
            final_state = app.invoke(
                {"original_input_prompt": final_prompt, "messages": []},
                {"recursion_limit": 60}
            )
            print(f" [{sql_id}] Graph 结束。 ")

            #  (V41 核心: 强制重执行提取)
            final_state_messages = final_state.get('messages')

            # 1. 获取 Agent 想要提交的 SQL
            submitted_sql = self._get_submitted_sql(final_state_messages)

            if submitted_sql:
                # 2. 强制现场执行 (不管历史记录里有没有)
                # print(f" [{sql_id}] 正在强制执行最终提交的 SQL 以确保结果一致性... ")
                with DB_LOCK:
                    final_result_str = sql_tool_instance.run(submitted_sql)

                # 3. 解析结果
                if not final_result_str.strip().startswith("Error"):
                    try:
                        final_result_obj = json.loads(final_result_str)
                        # 保存
                        self._save_log_files(log_dir, sql_id, final_state, submitted_sql)
                        return { "sql_id": sql_id, "sql": submitted_sql, "result": final_result_obj }
                    except json.JSONDecodeError:
                        print(f"!!! [{sql_id}] 最终 SQL 执行结果解析失败。")
                else:
                    print(f"!!! [{sql_id}] 最终 SQL 执行报错: {final_result_str}")

            # 如果没找到 SQL 或者执行失败
            print(f"!!! [{sql_id}] 任务失败: 无法提取或执行最终 SQL。")
            return None

        except Exception as e:
            print(f"!!! [{sql_id}] 崩溃: {e}")
            self._save_log_files(log_dir, sql_id, final_state, f"CRASH: {e}")
            return None

    def _save_log_files(self, log_dir, sql_id, final_state, extracted_sql):
        messages = final_state.get('messages', [])
        final_answer = messages[-1].content if messages else "N/A"

        with open(os.path.join(log_dir, "_FINAL_ANSWER.sql"), 'w', encoding='utf-8') as f:
            f.write(str(extracted_sql))

        log_data = {
            "sql_id": sql_id,
            "final_answer": final_answer,
            "sql": extracted_sql,
            "history": [msg.model_dump() for msg in messages]
        }
        with open(os.path.join(log_dir, "_FINAL_AGENT_RESULT.json"), 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=4)


# 主执行逻辑


def thread_safe_save(result_dict: Dict, output_path: str):
    with FILE_LOCK:
        try:
            existing_data = []
            if os.path.exists(output_path):
                with open(output_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)

            final_data = [item for item in existing_data if item.get('sql_id') != result_dict['sql_id']]
            final_data.append(result_dict)
            final_data.sort(key=lambda x: int(x.get('sql_id', '0').split('_')[1]) if '_' in x.get('sql_id', '') else 0)

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=4, cls=DecimalEncoder)
            print(f" [Save] {result_dict['sql_id']} 已保存。 ")
            return True
        except Exception as e:
            print(f"!!! [Save Error] {result_dict['sql_id']} 保存失败: {e}")
            return False

def worker_routine(task: Dict, coordinator: LangGraphCoordinator, output_file: str, ignore_cache: bool, cache_only: bool = False):
    try:
        result = coordinator.run_task(task, ignore_cache, cache_only)
        if result:
            return thread_safe_save(result, output_file)
    except Exception as e:
        print(f"!!! [Thread Error] {task.get('sql_id')}: {e}")
    return False

def main():
    parser = argparse.ArgumentParser(description="DeepSeek Only - LangGraph Final")
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--run_golden', action='store_true')
    parser.add_argument('--output_file', type=str, default=os.path.join(config.OUTPUT_DIR, "dataset_exe_result.json"))
    parser.add_argument('--rerun_ids', type=str, default=None)
    parser.add_argument('--update_file', action='store_true')
    parser.add_argument('--max_workers', type=int, default=1)
    parser.add_argument('--ignore_cache', action='store_true', help="强制 Agent 重新生成 SQL")
    parser.add_argument('--cache_only', action='store_true', help="仅执行已有答案 SQL，不调用模型 API")
    parser.add_argument('--model_name', default=None, help="模型名称，默认读取 DEEPSEEK_MODEL（deepseek-flash）")

    args = parser.parse_args()
    if args.max_workers < 1 or (args.limit is not None and args.limit < 1):
        parser.error('--max_workers 和 --limit 必须为正整数')
    if args.cache_only and args.ignore_cache:
        parser.error('--cache_only 与 --ignore_cache 不能同时使用')

    try:
        from execution_tools import DecimalEncoder as CustomEncoder, test_connection
    except ImportError:
        print("Error: execution_tools.py not found.")
        return

    print(" [Setup] 测试数据库... ")
    if not test_connection():
        return 1

    correct_answers = load_correct_answers(ANSWER_KEY_FILE)
    error_result_blacklist = load_error_result_blacklist(ERROR_SAMPLES_FILE)

    retriever = SchemaRetriever()
    builder = PromptBuilder()

    try:
        with open(DATASET_PATH, 'r', encoding='utf-8') as f:
            all_tasks = json.load(f)
    except Exception as e:
        print(f"加载任务失败: {e}")
        return 1

    tasks_to_run = []
    if args.rerun_ids:
        target_ids = {sql_id.strip() for sql_id in args.rerun_ids.split(',') if sql_id.strip()}
        unknown_ids = target_ids - {t.get('sql_id') for t in all_tasks}
        if unknown_ids:
            parser.error(f"未知题目 ID: {', '.join(sorted(unknown_ids))}")
        tasks_to_run = [t for t in all_tasks if t.get("sql_id") in target_ids]
    elif args.run_golden:
        tasks_to_run = [t for t in all_tasks if t.get("golden_sql")]
    else:
        tasks_to_run = [t for t in all_tasks if not t.get("golden_sql")]
    if args.cache_only:
        if args.rerun_ids:
            uncached_ids = target_ids - set(correct_answers)
            if uncached_ids:
                parser.error(f"这些题目没有正确答案缓存: {', '.join(sorted(uncached_ids))}；可移除 --cache_only 调用模型")
        tasks_to_run = [t for t in tasks_to_run if t.get('sql_id') in correct_answers]

    if args.limit:
        tasks_to_run = tasks_to_run[:args.limit]
    if not tasks_to_run:
        print('没有符合条件的题目。')
        return 1
    needs_model = not args.cache_only and (args.ignore_cache or any(
        t.get('sql_id') not in correct_answers for t in tasks_to_run
    ))
    try:
        llm = load_deepseek_model(args.model_name) if needs_model else None
    except ValueError as e:
        print(e)
        return 1

    coordinator = LangGraphCoordinator(
        llm_model=llm,
        retriever=retriever,
        builder=builder,
        correct_answers_map=correct_answers,
        error_result_blacklist=error_result_blacklist
    )

    print(f"\n{'*'*80}\n [Start] 准备并发处理 {len(tasks_to_run)} 个任务 (DeepSeek, Workers={args.max_workers})... \n{'*'*80}")
    if args.ignore_cache:
        print(" [Config] 已开启 --ignore_cache：将强制 Agent 重新运行所有任务 ")

    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(worker_routine, task, coordinator, args.output_file, args.ignore_cache, args.cache_only)
            for task in tasks_to_run
        ]
        concurrent.futures.wait(futures)
        success_count = sum(bool(future.result()) for future in futures)

    duration = time.time() - start_time
    print(f"\n{'*'*80}\n [End] 任务完成。耗时: {duration:.2f}秒 \n{'*'*80}")
    print(f"成功: {success_count}/{len(tasks_to_run)}；结果文件: {os.path.abspath(args.output_file)}")
    return 0 if success_count == len(tasks_to_run) else 1

if __name__ == "__main__":
    raise SystemExit(main())
