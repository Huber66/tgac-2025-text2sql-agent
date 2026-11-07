"""Compare a demo run to the synthetic fixture, ignoring row and column names."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from main import canonicalize_result_v4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, default=ROOT / 'output/demo/dataset_exe_result.json')
    parser.add_argument('--ids', default=None, help='Comma-separated expected IDs; default: both demo questions')
    args = parser.parse_args()
    expected = {r['sql_id']: r for r in json.loads((ROOT / 'data/demo/answer_key.json').read_text(encoding='utf-8'))}
    selected = set(args.ids.split(',')) if args.ids else set(expected)
    if not selected <= set(expected):
        parser.error('Unknown demo ID')
    actual = {r['sql_id']: r for r in json.loads(args.file.read_text(encoding='utf-8'))}
    matched = 0
    for sql_id in sorted(selected):
        valid = sql_id in actual and canonicalize_result_v4(actual[sql_id].get('result')) == canonicalize_result_v4(expected[sql_id]['result'])
        matched += int(valid)
        print(f'[{"PASS" if valid else "FAIL"}] {sql_id}')
    return 0 if matched == len(selected) else 1


if __name__ == '__main__':
    raise SystemExit(main())
