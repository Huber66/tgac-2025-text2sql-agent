# Contributing

For a runtime change, explain the failing command or input and include a regression test when behavior changes. Run:

```bash
python -m unittest discover -s tests -v
python scripts/check_public_files.py
```

Use the synthetic demo to report issues. Do not attach API keys, `.env`, original competition assets, complete execution logs or model conversation histories to a public issue or pull request.

Include the commands used for validation and their output. Identify whether a run used cached SQL, scripted tool calls, or fresh model inference.
