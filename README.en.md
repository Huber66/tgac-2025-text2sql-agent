# TGAC 2025 Text-to-SQL Agent

[中文](README.md) · English · [Architecture](docs/architecture.md) · [Reproduction](docs/reproduction.md)

A Python / LangGraph / DeepSeek / StarRocks implementation developed for the **2025 Tencent Games Algorithm Competition, Track 3: Data Intelligence Decision Science**. It combines task-specific schema context, business logic guides, SQL execution feedback, known-error result checks and final-query re-execution.

The public repository includes an independently created synthetic demo. It does not redistribute the original competition data, private credentials, execution logs or raw submissions.

## Design notes

The original materials describe limited reference SQL and noisy, mixed mock data. The implementation therefore emphasizes inspecting database samples, injecting explicit business constraints, and separating SQL execution errors from known incorrect results. It does not contain an SFT pipeline or a comparison proving one approach superior.

The expanded [solution notes](docs/solution.md), [knowledge lifecycle](docs/solution.md#运行时流程与知识维护流程), [material-to-code review](docs/materials-review.md), and [project discussion guide](docs/interview-guide.md) are in Chinese.

## Try the synthetic demo

Use Python 3.12 and Docker with Compose. Create and activate a virtual environment, then run:

```bash
pip install -r requirements-lock.txt
docker compose up -d --wait --wait-timeout 240
python reset_and_init_db.py --mode init
python main.py --cache_only
python scripts/verify_demo.py
```

This executes two cached SQL queries against real StarRocks tables without calling a model. The fixtures cover a tagged-player aggregate and next-day retention. They verify the runtime, not competition performance.

## Replay the feedback loop without an API key

After initializing the demo database:

```bash
python scripts/replay_demo.py
python scripts/verify_demo.py --file output/demo/replay_result.json --ids sql_1
```

The script runs six predefined tool calls through the real graph and database: inspect rows, execute an intentionally wrong date, reject the known empty result, revise the plan, execute the correct SQL and submit it. Final-query re-execution brings the SQL execution count to four. SQL choices are scripted; this is not evidence of autonomous model reasoning. See the [walkthrough](docs/walkthrough.md) and [recorded synthetic trace](examples/replay_trace.json).

## Generate fresh SQL

To generate fresh SQL, copy `.env.example` to `.env`, set `DEEPSEEK_API_KEY`, then run:

```bash
python main.py --ignore_cache --rerun_ids sql_1 --output_file output/demo/agent_result.json
python scripts/verify_demo.py --file output/demo/agent_result.json --ids sql_1
```

Fresh generation consumes API credits. The current default is `deepseek-flash`; configure `DEEPSEEK_MODEL` to change it. VS Code launch configurations are included.

## Design boundaries

Schema is selected by the task's supplied table list, not by a vector index. The error-result interceptor is heuristic and has a retry limit; successful execution is not proof of semantic correctness. SQL execution is serialized by a database lock, while model requests can be concurrent.

Authorized local competition artifacts can be imported with `scripts/prepare_competition_data.py` and used through `TGAC_PROFILE=competition`; see the [reproduction guide](docs/reproduction.md).

## License

[MIT](LICENSE) for this repository's source, documentation and synthetic data. External assets retain their own terms. See [NOTICE](NOTICE.md) and the [same-track repository references](docs/open-source-references.md).
