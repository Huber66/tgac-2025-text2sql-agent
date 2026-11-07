"""Import an authorized local bundle without copying credentials or logs."""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True,
                        help='Path to original code/ or final_for_student/ directory')
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    bundle = source / 'final_for_student' if (source / 'final_for_student').is_dir() else source
    artifacts = source if bundle != source else source.parent
    destination = ROOT / 'data' / 'competition'
    required = ('data/schema.json', 'data/common_knowledge.md', 'data/final_dataset.json',
                'data/insert_sql.json', 'sql_file/create_table.sql')
    for name in required:
        path = bundle / name
        if not path.is_file():
            parser.error(f'Missing required file: {path}')
        if path.suffix == '.json':
            json.loads(path.read_text(encoding='utf-8'))
    if destination.exists() and any(destination.iterdir()):
        parser.error('data/competition/ already contains files; choose a fresh checkout or back up it first.')
    for name in required:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle / name, target)
    for name, default in (('answer_key.json', []), ('error_samples.json', []), ('logic_guides.json', {})):
        original = artifacts / name
        value = json.loads(original.read_text(encoding='utf-8')) if original.is_file() else default
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Prepared local artifacts in {destination}. This directory is ignored by Git.')
    print('Set TGAC_PROFILE=competition before database initialization and inference.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
