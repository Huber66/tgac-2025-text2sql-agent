import json
import os
import sys
import argparse
import time
import config
from typing import List, Dict, Any, Optional

#  第三方库
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

#  本地模块适配
# 获取当前脚本所在目录 (code/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# 尝试导入 SchemaRetriever
try:
    from prompt_engine import SchemaRetriever
except ImportError:
    print("错误：无法导入 prompt_engine.SchemaRetriever。请确保 prompt_engine.py 在同一目录下。")
    sys.exit(1)

# 加载环境变量
DEEPSEEK_API_KEY = config.DEEPSEEK_API_KEY
DEEPSEEK_API_BASE = config.DEEPSEEK_API_BASE


# 1. 路径配置 (所有 JSON 都在 code/ 目录下)


# 逻辑指引文件 (输出)
LOGIC_GUIDES_FILE = config.LOGIC_GUIDES_FILE

# 答案库文件 (输入 - 用于逆向工程)
ANSWER_KEY_FILE = config.ANSWER_KEY_FILE

# 原始题目文件 (输入)
# 默认认为 final_dataset.json 也在 code/ 目录下
DATASET_PATH = config.DATASET_PATH

# 容错：如果 code/ 下没有题目文件，尝试去 config 指向的地方找（如果有 config.py）
if not os.path.exists(DATASET_PATH):
    try:
        import config
        if os.path.exists(config.DATASET_PATH):
            DATASET_PATH = config.DATASET_PATH
    except ImportError:
        pass

print(f" [Config] 题目文件路径: {DATASET_PATH}")
print(f" [Config] 答案库路径:   {ANSWER_KEY_FILE}")
print(f" [Config] 逻辑指引路径: {LOGIC_GUIDES_FILE}")

#  2. Prompt 模板

SYSTEM_PROMPT = """你是一个世界级的 Text-to-SQL 专家和数据架构师。
你的任务不是写 SQL，而是分析题目和（可选的）正确 SQL，提炼出其中的**业务逻辑**、**陷阱**和**强制规则**。
你的输出将作为 "Logic Guide" 注入到另一个 AI Agent 的上下文窗口中，帮助它做对题目。
请务必简洁、精准、直击要害。
"""

# 模式 A: 有正确 SQL -> 逆向分析
PROMPT_REVERSE_ENGINEERING = """
### 任务目标：逆向工程 (Reverse Engineering)
这是一道【已解决】的题目。请分析下面的【参考正确 SQL】，解释它是如何正确解决问题的。

### 题目信息
**ID**: {sql_id}
**问题**: {question}
**特定知识 (Knowledge)**: {knowledge}

### 数据库 Schema
{schema_text}

### 参考正确 SQL (Golden/Correct SQL)
```sql
{correct_sql}
```

### 你的分析任务
请总结出 3-5 条关键的逻辑规则。
重点关注：
1. **数据过滤 (指纹)**: SQL 中是否有硬编码的 ID、类型或状态？(例如 `type=2`, `status='completed'`)
2. **表连接 (JOIN 铁律)**: 它是如何关联表的？有没有使用特殊的桥接表？使用了 LEFT JOIN 还是 INNER JOIN？
3. **计算逻辑**: 如果有 `CASE WHEN`，请提取分类逻辑。如果有留存/活跃计算，请解释其公式。
4. **陷阱规避**: 它避免了什么常见的错误？(例如：使用了 `vplayerid` 而不是 `uid`)

### 输出格式 (请严格遵守)
【逻辑锁定】
1. **[关键词]**: 规则描述...
2. **[关键词]**: 规则描述...
"""

# 模式 B: 无正确 SQL -> 先验分析
PROMPT_PREDICTIVE_ANALYSIS = """
### 任务目标：先验分析 (Predictive Analysis)
这是一道【未解决】的难题。请根据题目描述和 Schema，预判可能的解题思路和陷阱。

### 题目信息
**ID**: {sql_id}
**问题**: {question}
**特定知识 (Knowledge)**: {knowledge}

### 数据库 Schema
{schema_text}

### 你的分析任务
请制定 3-5 条解题指导原则。
重点关注：
1. **语义消歧**: 分析题目中的模糊词（如“最”、“近期”），给出 SQL 定义（如 `ROW_NUMBER()`, `datediff <= 30`）。
2. **路径规划**: 根据 Schema，推测最合理的表连接路径。
3. **Knowledge 转化**: 将题目提供的 Knowledge 转化为具体的 `WHERE` 条件或 `CASE WHEN` 逻辑。
4. **防御性编程**: 提示可能的数据陷阱（如 NULL 值处理、ID 格式不一致）。

### 输出格式 (请严格遵守)
【逻辑预判】
1. **[关键词]**: 规则描述...
2. **[关键词]**: 规则描述...
"""

class LogicGenerator:
    def __init__(self):
        print(f" [Init] 初始化逻辑提炼器 (DeepSeek Only) ")

        # 1. 加载 LLM (本地配置)
        self.llm = self._load_deepseek_model()

        # 2. 初始化 SchemaRetriever
        self.retriever = SchemaRetriever()

        # 3. 加载数据
        self.dataset = self._load_json(DATASET_PATH)
        self.answer_key = self._load_json(ANSWER_KEY_FILE)
        self.logic_guides = self._load_json(LOGIC_GUIDES_FILE)

        # 4. 构建 correct_sql 映射
        self.correct_sql_map = {}
        self._build_correct_map()

    def _load_deepseek_model(self):
        """本地加载 DeepSeek 模型"""
        if not DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY 未设置")

        return ChatOpenAI(
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_API_BASE,
            temperature=0.7, # 生成逻辑指引时需要一点创造力来总结
            max_tokens=8192,
            timeout=120,
            max_retries=1,
            extra_body={"thinking": {"type": "disabled"}},
        )

    def _load_json(self, path: str) -> Any:
        if not os.path.exists(path):
            # 如果是 logic_guides.json 不存在，返回空字典；如果是 dataset 不存在，返回空列表
            return {} if "guides" in path else []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取文件失败 {path}: {e}")
            return {} if "guides" in path else []

    def _build_correct_map(self):
        # 1. 从 answer_key.json 加载
        if isinstance(self.answer_key, list):
            for item in self.answer_key:
                if item.get("status") == "correct":
                    self.correct_sql_map[item['sql_id']] = item.get("query") or item.get("sql")

        # 2. 从数据集本身加载 Golden SQL (如果 dataset 里包含 sql 字段)
        if isinstance(self.dataset, list):
            for task in self.dataset:
                if task.get("golden_sql") and task.get("sql"):
                    self.correct_sql_map[task['sql_id']] = task["sql"]

        print(f" [Init] 已索引 {len(self.correct_sql_map)} 条正确 SQL ")

    def save_guide(self, sql_id: str, content: str):
        # 重新加载以防覆盖（简单的并发保护）
        current_data = self._load_json(LOGIC_GUIDES_FILE)
        if isinstance(current_data, list): current_data = {}

        current_data[sql_id] = content

        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(LOGIC_GUIDES_FILE)), exist_ok=True)

        with open(LOGIC_GUIDES_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=4)
        print(f"   -> 已保存 {sql_id}")

    def process_task(self, task: Dict[str, Any]):
        sql_id = task['sql_id']
        question = task['question']
        knowledge = task.get('knowledge', '')
        table_list = task.get('table_list', [])

        # 获取 Schema 上下文
        schema_text = self.retriever.get_relevant_schema_as_text(table_list)

        # 判断模式
        correct_sql = self.correct_sql_map.get(sql_id)

        if correct_sql:
            print(f" 处理 {sql_id} (逻辑指引生成) ")
            prompt = PROMPT_REVERSE_ENGINEERING.format(
                sql_id=sql_id,
                question=question,
                knowledge=knowledge,
                schema_text=schema_text,
                correct_sql=correct_sql
            )
        else:
            print(f" 处理 {sql_id} (先验分析) ")
            prompt = PROMPT_PREDICTIVE_ANALYSIS.format(
                sql_id=sql_id,
                question=question,
                knowledge=knowledge,
                schema_text=schema_text
            )

        try:
            # 调用 LLM
            response = self.llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ])

            guide_content = response.content.strip()
            # 清理 Markdown
            guide_content = guide_content.replace("```markdown", "").replace("```", "").strip()

            self.save_guide(sql_id, guide_content)

        except Exception as e:
            print(f"!!! 生成失败 {sql_id}: {e}")

    def run(self, mode: str, ids: str = None, overwrite: bool = False):
        target_tasks = []

        # 筛选任务
        if ids:
            id_set = set(ids.split(','))
            target_tasks = [t for t in self.dataset if t['sql_id'] in id_set]
        elif mode == 'golden':
            target_tasks = [t for t in self.dataset if t.get('golden_sql')]
        elif mode == 'correct':
            target_tasks = [t for t in self.dataset if t['sql_id'] in self.correct_sql_map]
        elif mode == 'unsolved':
            target_tasks = [t for t in self.dataset if t['sql_id'] not in self.correct_sql_map]
        elif mode == 'all':
            target_tasks = self.dataset

        print(f" 开始处理 {len(target_tasks)} 个任务 ")

        for task in target_tasks:
            # 检查是否已存在 (除非指定特定 ID 或 开启覆盖，否则跳过已存在的)
            if not overwrite and not ids and task['sql_id'] in self.logic_guides:
                print(f"   [跳过] {task['sql_id']} 已存在")
                continue

            self.process_task(task)
            time.sleep(1) # 避免速率限制

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自动生成逻辑指南")
    parser.add_argument('--mode', type=str, default="ids", choices=['golden', 'correct', 'unsolved', 'all', 'ids'], help="运行模式")
    parser.add_argument('--ids', type=str, help="指定 ID 列表，逗号分隔")
    parser.add_argument('--overwrite', action='store_true', help="强制重新生成")

    args = parser.parse_args()

    generator = LogicGenerator()
    generator.run(mode=args.mode, ids=args.ids, overwrite=args.overwrite)
