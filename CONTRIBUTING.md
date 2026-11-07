# Contributing

For a runtime change, explain the failing command or input and include a regression test when behavior changes. Run:

```bash
python -m unittest discover -s tests -v
python scripts/check_public_files.py
```

Use the synthetic demo to report issues. Do not attach API keys, `.env`, original competition assets, complete execution logs or model conversation histories to a public issue or pull request.

Changes should preserve the distinction between cached SQL execution and fresh model inference. Describe validation as local tests or demo checks; do not report them as competition scores.
