# 本地复现

## 环境

- Python 3.12；依赖版本见 `requirements-lock.txt`。
- Docker Engine / Docker Desktop，支持 `docker compose up --wait`。
- 容器配置上限为 4 GB，FE 堆上限 1 GB。StarRocks 镜像固定摘要，避免浮动标签改变运行环境。
- `demo` 使用 `tgac_demo`，`competition` 默认使用 `tgac_contest`；输出也分别存放。

## Windows PowerShell

在仓库根目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Action Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Action StartDb
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Action InitDb
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Action Cached
.\.venv\Scripts\python.exe scripts\verify_demo.py
```

`InitDb` 只在首次使用空数据库时运行。已存在表时会报错退出，不会直接删除。后续启动 `StartDb` 并运行 `Cached` 即可。

要演示模型：

```powershell
Copy-Item .env.example .env
# 在编辑器中填写 DEEPSEEK_API_KEY
.\run.ps1 -Action Agent -SqlIds sql_1
.\.venv\Scripts\python.exe scripts\verify_demo.py --file output/demo/agent_result.json --ids sql_1
```

PowerShell 的执行策略若阻止短命令，可继续使用上面的 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File` 形式，无需修改系统的全局执行策略。

## Linux / macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
docker compose up -d --wait --wait-timeout 240
python reset_and_init_db.py --mode init
python main.py --cache_only
python scripts/verify_demo.py
```

先确认 Docker 能在本机运行镜像；容器平台或 CPU 指令集不匹配时需使用兼容环境。此发布版本的数据库演示在 Windows + Docker Desktop 的 Linux 容器上验证；Linux CI 验证 Python 依赖与运行时测试，不代替所有平台上的数据库演示。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TGAC_PROFILE` | `demo` | `demo` 或 `competition` |
| `TGAC_DATA_DIR` | `data/<profile>` | 可选的资料根目录 |
| `DEEPSEEK_API_KEY` | 无 | 仅模型调用需要 |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 模型名称 |
| `DB_HOST` | `127.0.0.1` | 数据库地址 |
| `DB_PORT` | `19030` | 宿主机 SQL 端口；也用于 Compose 端口映射 |
| `DB_USER` / `DB_PASSWORD` | `root` / 空 | 本地演示数据库账户 |
| `DB_NAME` | 随 profile 切换 | 显式设置后会覆盖默认数据库名称 |

Python 从仓库根目录的 `.env` 加载配置，进程中已有环境变量优先。不要提交真实 `.env`。`run.ps1` 的 `-Profile` 参数明确设置模式，优先于 `.env`。

## 接入本地比赛资料

先自行准备有权使用的原始 `code/` 或 `final_for_student/` 目录。仓库不从其他参赛队下载比赛资料。

```bash
python scripts/prepare_competition_data.py --source /path/to/original/code
```

脚本白名单复制必需的数据 JSON、公共知识和建表 SQL，并可导入本地答案库、错误样本和逻辑指引。不会复制 `.env`、PDF、Notebook、历史日志或原始提交结果。目标 `data/competition/` 已加入 `.gitignore`。

在 `.env` 设置 `TGAC_PROFILE=competition`，并移除为演示显式设置的 `DB_NAME`，或另设比赛数据库名称。随后：

```bash
python reset_and_init_db.py --mode init
python check_environment.py
python main.py --cache_only
python main.py --ignore_cache --rerun_ids sql_1 --limit 1 --max_workers 1
```

Windows 包装脚本需要对应传入 `-Profile competition`：

```powershell
.\run.ps1 -Action InitDb -Profile competition
.\run.ps1 -Action Cached -Profile competition
.\run.ps1 -Action Agent -Profile competition -SqlIds sql_1
```

完整生成可用 `python main.py --ignore_cache --max_workers 1`；该命令会对符合条件的全部题目调用模型，请根据需要限制 `--limit`。默认不运行带 `golden_sql` 的题目，`--run_golden` 可单独选择它们。

## 常用入口

| 目的 | 命令 |
| --- | --- |
| 只检查环境和数据库 | `python check_environment.py` |
| 执行全部已有正确 SQL | `python main.py --cache_only` |
| 强制模型处理指定题 | `python main.py --ignore_cache --rerun_ids sql_1,sql_2` |
| 更换模型 | `python main.py --ignore_cache --model_name deepseek-v4-pro --limit 1` |
| 查看答案库状态 | `python manage_answers.py status` |
| 对比本地结果 | `python manage_answers.py test` |
| 从已有正确答案生成指引 | `python generate_logic_guide.py --mode correct` |
| 停止并保留数据库数据 | `docker compose stop` |

`--update_file` 保留为旧命令的兼容参数；当前写入始终逐题更新，不依赖该参数。

数据库初始化检查源文件，并在建表或数据导入失败时退出。确需清空所配置的数据库时，可执行 `python reset_and_init_db.py --mode init --force`；应先确认 `DB_NAME` 并备份所需内容。

## 故障定位

- **连不上数据库**：确认 `docker compose ps` 为 healthy，并核对 `DB_PORT`；本仓库默认 19030，不是原比赛项目的 9030。
- **找不到资料**：检查 `TGAC_PROFILE` 与 `TGAC_DATA_DIR`；默认 demo 不依赖外部文件。
- **没有缓存**：`--cache_only` 仅处理答案库；指定无缓存的 ID 会报错，改用模型运行时移除此参数。
- **API 报错**：检查密钥、模型名称、账户额度与网络。图流程失败会返回非零状态，不代表产生了有效答案。
- **初始化提示已有表**：正常情况下直接复用数据库，不需要再次导入。

输出保存在 `output/<profile>/`，逐题运行记录在其中的 `api_langgraph_runs/`。报告问题时优先给出命令和删去敏感信息的报错摘要。
