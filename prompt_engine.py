import json
import sys
import os
import config
from typing import List, Dict, Optional

class SchemaRetriever:
    """
    负责从 schema.json 中加载和检索表结构。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SchemaRetriever, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, schema_path: str = config.SCHEMA_PATH):
        if self._initialized:
            return

        print(f"--- [SchemaRetriever] 正在从 {schema_path} 加载 schema... ---")
        self.schema_dict = {}

        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                full_schema = json.load(f)

            self.schema_dict = {
                table['table_name']: table for table in full_schema
            }
            print(f"--- [SchemaRetriever] 成功加载 {len(self.schema_dict)} 张表的 schema。 ---")

        except FileNotFoundError:
            print(f"错误: schema 文件未找到 {schema_path}")
        except json.JSONDecodeError:
            print(f"错误: 无法解析 {schema_path}。")

        self._initialized = True

    def get_table_schema(self, table_name: str) -> Optional[Dict]:
        """获取单个表的 schema 字典。"""
        return self.schema_dict.get(table_name)

    def get_relevant_schema_as_text(self, table_list: List[str]) -> str:
        """
        获取表列表的相关 schema。
        只显示当前表的原始描述，不进行全局补全。
        """
        if not self.schema_dict:
            return "错误：Schema 未加载。"

        formatted_schemas = []
        for table_name in table_list:
            table_info = self.get_table_schema(table_name)
            if table_info:
                s = f"表名: {table_name}\n"
                s += f"描述: {table_info.get('table_description', 'N/A')}\n"
                s += "字段:\n"
                for col in table_info.get('columns', []):

                    col_name = col.get('col', 'unknown_col')
                    col_type = col.get('type', 'unknown_type')
                    # 直接获取当前表的描述，如果没有则显示 N/A
                    description = col.get('description')
                    if not description or not description.strip():
                        description = "N/A"

                    s += f"  - {col_name} ({col_type}): {description}\n"
                formatted_schemas.append(s)
            else:
                formatted_schemas.append(f"表 '{table_name}' 未在 schema.json 中找到。\n")

        return "\n".join(formatted_schemas)


class PromptBuilder:
    """
    负责组装 Agent 的最终提示词 (System Prompt)。
    集成 Logic Guides (逻辑指引) 与 Golden SQL 规则。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PromptBuilder, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, knowledge_path: str = config.KNOWLEDGE_PATH):
        if self._initialized:
            return

        # 1. 加载通用知识
        print(f"--- [PromptBuilder] 正在从 {knowledge_path} 加载通用知识... ---")
        try:
            with open(knowledge_path, 'r', encoding='utf-8') as f:
                self.common_knowledge_content = f.read()
            print(f"--- [PromptBuilder] 通用知识加载成功。 ---")
        except FileNotFoundError:
            print(f"错误: 通用知识文件未找到 {knowledge_path}")
            self.common_knowledge_content = "错误：通用知识文件未找到。"

        logic_guides_path = config.LOGIC_GUIDES_FILE
        self.logic_guides = {}

        print(f"--- [PromptBuilder] 正在加载逻辑指引: {logic_guides_path} ... ---")
        if os.path.exists(logic_guides_path):
            try:
                with open(logic_guides_path, 'r', encoding='utf-8') as f:
                    self.logic_guides = json.load(f)
                print(f"--- [PromptBuilder] 成功加载 {len(self.logic_guides)} 条逻辑指引。 ---")
            except Exception as e:
                print(f"--- [PromptBuilder] 加载逻辑指引失败: {e} ---")
        else:
            print(f"--- [PromptBuilder] 未找到逻辑指引文件 (如果是初次运行可忽略)。 ---")

        self._initialized = True

    def build_agent_input(
        self,
        sql_id: str,  # 需要 sql_id 来查找对应的逻辑指引
        question: str,
        relevant_schema_string: str,
        task_specific_knowledge: str
    ) -> str:
        """
        组装最终 Prompt。
        自动注入 sql_id 对应的 Logic Guide（如果有）。
        """

        if not task_specific_knowledge or task_specific_knowledge.isspace():
            task_specific_knowledge = "无"

        # 获取逻辑指引
        logic_guide_content = self.logic_guides.get(sql_id, "")
        logic_guide_section = ""

        if logic_guide_content:
            logic_guide_section = f"""
3.  LOGIC GUARDRAILS (逻辑指引 - 最高优先级):
(!!! 如果本节内容与 Question 或 Knowledge 有冲突，请无条件遵循本节的指示 !!!)
{logic_guide_content}
"""
        else:
            logic_guide_section = "3. LOGIC GUARDRAILS:\n(此任务无特殊逻辑指引)"

        final_input = f"""
--- 你的最高指示 (不可遗忘，必须在每一步都重新阅读) ---

1. USER'S QUESTION:
{question}

2. TASK-SPECIFIC KNOWLEDGE:
(此知识对此特定问题至关重要)
{task_specific_knowledge}
{logic_guide_section}
4. RELEVANT TABLE SCHEMAS:
(这是你在此任务中应该使用的表，不一定每个都需要，根据你自己判断)
{relevant_schema_string}

5. GENERAL DATABASE KNOWLEDGE:
(此知识适用于问题)
{self.common_knowledge_content}

6. CRITICAL SQL RULES (Golden Rules):
(这是基于官方标准答案总结出的“铁律”，必须严格遵守)
---
**(1) 位图处理 (cbitmap)**:
   * **禁止**使用位运算。`cbitmap` 是由 '0' 和 '1' 组成的字符串。
   * **必须**使用字符串函数处理。例如：判断第 N 天是否活跃，使用 `instr(substr(cbitmap, N, 1), '1') > 0`。
   * 统计流失/回流时，使用 `substr(cbitmap, start, len)` 截取特定段。

**(2) 留存计算 (Retention)**:
   * **禁止**使用复杂的 `IN` 或 `EXISTS` 子查询计算留存。
   * **必须**使用自关联 (`LEFT JOIN`)。
   * 范式：`FROM table a LEFT JOIN table b ON a.uid = b.uid AND date_add(a.date, N) = b.date`。
   * 然后统计 `COUNT(DISTINCT b.uid)`。

**(3) 排除与否定 (Exclusion)**:
   * 如果要找“新玩家”或“未参与的用户”，**优先**使用 `LEFT JOIN ... WHERE b.uid IS NULL`。

**(4) 排名与去重 (Ranking)**:
   * 如果题目要求“主玩”、“首次”、“最近一次”等唯一性记录。
   * **优先**使用 `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` 进行筛选，而不是简单的 `GROUP BY`。

**(5) 日期与时间**:
   * 这里的日期通常是字符串格式（如 '20240723'）。
   * 提取月份优先使用 `substr(date, 1, 6)`。

**(6) 占比与数值格式 (Formatting)**:
   * **比率/占比**：凡是题目要求“占比”、“比率”或“百分比”的，**严禁**输出带 '%' 的字符串。**必须输出小数** (Decimal)。
   * **精度**：除非另有说明，涉及除法的计算请使用 `ROUND(x, 2)` 保留两位小数。
   * **整数**：如果结果是计数（Count），请确保是整数类型。

**(7) 列名与顺序 (Columns)**:
   * **列名不影响评分**：评分系统只校对值的**内容**和**顺序**。你不必为了匹配题目中的中文列名而强行使用复杂的别名（AS ...）。
   * **顺序至关重要**：你生成的 SQL `SELECT` 子句中的字段顺序，必须与 `USER'S QUESTION` 中要求的“输出：...”顺序**完全一致**。

**(8) 慢思考与数据验证**:
   * **不要急于求成**。直接写出最终 SQL 的错误率极高。
   * 必须通过查询数据 (`LIMIT 50`) 来验证 ID 格式、日期格式和数据内容。
   * **不要**假设数据是干净的，要假设数据是“全量混合”的，必须通过 `WHERE` 过滤掉无关数据。
---


--- INSTRUCTIONS (Standard Operating Procedure) ---
你的目标是生成一个单一、最终、正确的 SQL 查询。

**(!!!) 协议铁律 (CRITICAL PROTOCOL) (!!!)**
1.  **严禁直接文本回复**：你绝对**不能**在对话中直接输出 SQL 或答案。
2.  **必须调用工具**：你与外部世界的**唯一**交互方式是调用工具。
3.  **结束标志**：只有调用 `submit_final_sql` 才算任务结束。如果你只输出了文本而没有调用这个工具，任务将被视为**失败**。

你拥有工具: `execute_sql_tool`, `revise_plan`, `submit_final_sql`.

你 *必须* 严格遵循以下三阶段思考过程，**严禁跳步**：

**阶段 1: 侦察与验证 (Reconnaissance & Verification)**
* **(!!!) 绝对禁止在第一步就尝试写出最终的复杂 SQL。**
* 你必须先通过 `execute_sql_tool` 执行 1 到 2 个简单的 **“探查查询”**。
    * 例如：`SELECT column_name FROM table LIMIT 50`。
* **目的**：
    1. 验证你在 `Knowledge` 中看到的 ID 是否真实存在于表中 (例如 `vplayerid` 还是 `suserid`)。
    2. 验证日期格式（是 '20240101' 还是 '2024-01-01'）。
    3. 验证字段是否有数据（避免全 NULL 列）。
    4. 寻找数据的“指纹”：例如某个游戏的所有 ID 是否都以特定字符开头。
* **只有当你亲眼看到了数据库返回的真实样本后，才能进入阶段 2。**

**阶段 2: 构建与修正 (Build & Correct)**
* 基于“阶段 1”看到的真实数据，构建你的完整 SQL。
* **行动：** 调用 `execute_sql_tool` 运行完整 SQL。
* **观察：** 收到结果或错误。
* **修正：** 如果报错，或者结果为空，利用 `revise_plan` 调整思路。
* **(!!!) 自我审查 (Self-Check):** * 检查 **列的顺序** 是否与题目要求*完全一致* (这是评分标准)。
    * 检查 **占比格式** 是否为小数 (禁止百分号)。
    * 检查数据量级是否合理。

**阶段 3: 提交 (Submit)**
* **停止条件：** 只有当你确认 SQL 语法正确、**自我审查通过**、且输出格式完全符合题目要求时。
* 在提交前，*必须*最后检查一次“列顺序”是否与题目要求一致。
* **最终行动：** 调用 `submit_final_sql`。**不要说话，直接调用工具。**

**现在的任务是：执行阶段 1。请先写一个简单的 LIMIT 50 查询来探查数据。**
--- 最高指示结束 ---
"""
        return final_input


# --- 用于测试的 __main__ 块 ---

def _load_task_data(sql_id: str) -> dict:
    try:
        with open(config.DATASET_PATH, 'r', encoding='utf-8') as f:
            all_tasks = json.load(f)
        for task in all_tasks:
            if task.get("sql_id") == sql_id:
                return task
        return None
    except Exception as e:
        print(f"加载任务数据时出错: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sql_id_to_test = sys.argv[1]
    else:
        sql_id_to_test = "sql_30"

    print(f"--- [TEST HARNESS] 正在为 {sql_id_to_test} 构建 Prompt ---")
    task_data = _load_task_data(sql_id_to_test)
    if not task_data:
        print(f"错误: 在 {config.DATASET_PATH} 中未找到 {sql_id_to_test}")
        sys.exit(1)

    question = task_data.get("question")
    table_list = task_data.get("table_list")
    knowledge = task_data.get("knowledge", "")

    try:
        # Test harness 现在使用内部定义的 SchemaRetriever
        retriever = SchemaRetriever()
        builder = PromptBuilder()
    except Exception as e:
        print(f"初始化依赖时出错: {e}")
        sys.exit(1)

    schema_text = retriever.get_relevant_schema_as_text(table_list)

    # (V36 Update) 现在 build_agent_input 需要 sql_id
    final_input_prompt = builder.build_agent_input(
        sql_id=sql_id_to_test,
        question=question,
        relevant_schema_string=schema_text,
        task_specific_knowledge=knowledge
    )

    print(f"\n\n--- [!!! 最终生成的 Agent Input (Prompt) for {sql_id_to_test} !!!] ---")
    print(final_input_prompt)
    print("--- [!!! PROMPT END !!!] ---")
