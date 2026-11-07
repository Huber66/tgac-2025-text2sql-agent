# TGAC 2025 Text-to-SQL Agent

**Champion · 2025 Tencent Games Algorithm Competition · Data Intelligence Decision Science Track**

[中文](README.md) · English · [Architecture](docs/architecture.md) · [Reproduction](docs/reproduction.md)

[Project showcase](https://huber66.github.io/projects/tgac.html)

A Python / LangGraph / DeepSeek / StarRocks implementation developed for the **2025 Tencent Games Algorithm Competition, Track 3: Data Intelligence Decision Science**. It combines task-specific schema context, business logic guides, SQL execution feedback, known-error result checks and final-query re-execution.

The repository includes the core implementation and an independently created synthetic demo. Local competition data can be used through the competition profile.

## Design notes

The design addresses limited reference SQL and noisy, mixed mock data by inspecting database samples, injecting explicit business constraints, and separating SQL execution errors from known incorrect results.

The [solution notes](docs/solution.md), [knowledge lifecycle](docs/solution.md#运行时流程与知识维护流程), [module index](docs/source-map.md), and [project guide](docs/project-guide.md) are in Chinese.

## Try the synthetic demo

Use Python 3.12 and Docker with Compose. Create and activate a virtual environment, then run:

```bash
pip install -r requirements-lock.txt
docker compose up -d --wait --wait-timeout 240
python reset_and_init_db.py --mode init
python main.py --cache_only
python scripts/verify_demo.py
```

This executes two cached SQL queries against real StarRocks tables without calling a model. The fixtures cover a tagged-player aggregate and next-day retention.

## Replay the feedback loop without an API key

After initializing the demo database:

```bash
python scripts/replay_demo.py
python scripts/verify_demo.py --file output/demo/replay_result.json --ids sql_1
```

The script runs six predefined tool calls through the real graph and database: inspect rows, execute an intentionally wrong date, reject the known empty result, revise the plan, execute the correct SQL and submit it. Final-query re-execution brings the SQL execution count to four. See the [walkthrough](docs/walkthrough.md) and [recorded synthetic trace](examples/replay_trace.json).

## Generate fresh SQL

To generate fresh SQL, copy `.env.example` to `.env`, set `DEEPSEEK_API_KEY`, then run:

```bash
python main.py --ignore_cache --rerun_ids sql_1 --output_file output/demo/agent_result.json
python scripts/verify_demo.py --file output/demo/agent_result.json --ids sql_1
```

Fresh generation consumes API credits. The current default is `deepseek-flash`; configure `DEEPSEEK_MODEL` to change it. VS Code launch configurations are included.

## Runtime flow

Schema is selected by the task's supplied table list. The error-result interceptor compares submitted results with known error samples and returns feedback through a bounded retry loop. SQL execution uses a database lock, while model requests can run concurrently.

Authorized local competition artifacts can be imported with `scripts/prepare_competition_data.py` and used through `TGAC_PROFILE=competition`; see the [reproduction guide](docs/reproduction.md).

## License

[MIT](LICENSE) for this repository's source, documentation and synthetic data. External assets retain their own terms. See [NOTICE](NOTICE.md) and the [same-track repository references](docs/open-source-references.md).
