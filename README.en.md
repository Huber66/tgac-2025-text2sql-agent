# TGAC 2025 Text-to-SQL Agent

[中文](README.md) · English · [Architecture](docs/architecture.md) · [Reproduction](docs/reproduction.md)

A Python / LangGraph / DeepSeek / StarRocks implementation developed for the **2025 Tencent Games Algorithm Competition, Track 3: Data Intelligence Decision Science**. It combines task-specific schema context, business logic guides, SQL execution feedback, known-error result checks and final-query re-execution.

The public repository includes an independently created synthetic demo. It does not redistribute the original competition data, private credentials, execution logs or raw submissions.

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
