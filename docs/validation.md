# 验证记录与范围

核对日期：2026-11-07。以下是开源版本的工程检查与演示记录，不是比赛成绩或泛化准确率。

## 本地检查

环境：Windows、Python 3.12、Docker Desktop Linux 容器、固定摘要的 StarRocks 3.5 镜像。公开演示使用独立 `tgac_demo` 数据库。

| 检查 | 结果 | 实际覆盖 |
| --- | --- | --- |
| 全新虚拟环境安装 | 通过 | 从锁定的运行时依赖清单安装，而非依赖全局 Python 环境 |
| 运行时回归测试 | 8 项通过 | 数值格式化、黑名单比较、空结果拦截、SQL 对应关系、无模型缓存执行、最终重执行、异常日志、已有库保护 |
| 自造资料初始化 | 通过 | 两张表、两条批量插入任务，共 11 行自造记录 |
| 不调用模型的演示 | 两题校验通过 | 实际执行聚合 SQL 与次日留存 SQL，并比较预期结果 |
| 固定工具序列的闭环回放 | 通过 | 6 次工具调用、4 次 SQL 查询；已知空结果拦截、修正规划、接受正确提交和最终重执行，结果与自造夹具一致 |
| DeepSeek 工具调用 | 单题校验通过 | `deepseek-flash` 在 `--ignore_cache` 下处理自造 `sql_1`，执行并提交最终 SQL |
| 本地比赛资料导入 | 通过 | 白名单资料复制到被 Git 忽略的目录，并使用原本的本地数据库完成缓存执行 |
| 公开文件检查 | 通过 | 版本控制中的文件不包含比赛资料、原始输出、真实 `.env` 或已知令牌格式 |

运行命令：

```bash
python -m pip check
python -m unittest discover -s tests -v
python main.py --cache_only
python scripts/verify_demo.py
python scripts/replay_demo.py
python scripts/verify_demo.py --file output/demo/replay_result.json --ids sql_1
python scripts/verify_demo.py --file output/demo/agent_result.json --ids sql_1
python scripts/check_public_files.py
docker compose config --quiet
```

## 自动检查

[GitHub Actions](https://github.com/Huber66/tgac-2025-text2sql-agent/actions/workflows/ci.yml) 在 Ubuntu + Python 3.12 上安装依赖，检查语法、运行回归测试、扫描公开文件，并校验 Compose 配置。CI 不调用付费模型，也不启动数据库进行集成演示。

## 不覆盖的内容

- 未进行全量模型推理、消融实验或正式比赛评测。
- 单题模型演示只能证明这一输入在当次调用中跑通，不能保证再次生成得到相同 SQL。
- 闭环回放的工具顺序与 SQL 已预设，只验证真实图与数据库的响应，不证明模型自行纠错。
- 缓存 SQL 回归与模型从头生成是不同验证，不能相互替代。
- 未验证所有操作系统、CPU 架构、模型版本和 StarRocks 版本。
- 文件检查用于发现常见误提交，不等于对全部潜在敏感信息提供保证。
