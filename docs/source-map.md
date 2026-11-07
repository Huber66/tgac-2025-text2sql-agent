# 模块与数据文件索引

## 代码模块

| 文件 | 主要职责 |
| --- | --- |
| `main.py` | 读取任务、调度 Agent、比较错误结果、重执行最终 SQL 并保存输出 |
| `prompt_engine.py` | 提取相关表结构，组装题目、业务知识和 Logic Guide |
| `execution_tools.py` | 连接 StarRocks，执行 SQL，格式化并记录结果 |
| `generate_logic_guide.py` | 从参考 SQL 或待分析题目中提炼逻辑指引 |
| `manage_answers.py` | 维护正确答案与错误样本，比较本地结果 |
| `reset_and_init_db.py` | 创建数据库表并导入数据 |
| `config.py` | 管理模型接口、数据库连接与数据模式 |

## 数据与输出

数据根目录由 `TGAC_PROFILE` 和 `TGAC_DATA_DIR` 决定，配置见[复现文档](reproduction.md)。

| 相对路径 | 内容 |
| --- | --- |
| `data/final_dataset.json` | 题目、表列表和特定知识 |
| `data/schema.json` | 表与字段结构 |
| `data/common_knowledge.md` | 通用业务知识 |
| `logic_guides.json` | 按题目 ID 保存的逻辑指引 |
| `answer_key.json` | 正确答案 SQL 与参考结果 |
| `error_samples.json` | 已知错误结果样本 |
| `sql_file/create_table.sql` | StarRocks 建表语句 |
| `data/insert_sql.json` | 数据插入语句 |

默认结果保存在 `output/<profile>/dataset_exe_result.json`，逐题日志保存在同一模式下的 `api_langgraph_runs/`。固定工具序列回放的结果与轨迹分别为 `replay_result.json` 和 `replay_trace.json`。
