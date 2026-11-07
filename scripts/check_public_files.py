"""Reject accidentally tracked local artifacts and common credential formats."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(rb'sk-[A-Za-z0-9_-]{20,}'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
)


def main():
    tracked = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT)
    names = sorted(set(p.decode('utf-8') for p in tracked.split(b'\0') if p))
    problems = []
    for name in names:
        path = ROOT / name
        local_path = (name.startswith(('data/competition/', 'output/', 'upload_example/', 'final_for_student/', '.venv/'))
                      or (path.name.startswith('.env') and path.name != '.env.example')
                      or path.suffix in {'.zip', '.ipynb', '.pem', '.key'}
                      or (path.name in {'answer_key.json', 'error_samples.json', 'logic_guides.json', 'dataset_exe_result.json'}
                          and not name.startswith('data/demo/')))
        if local_path:
            problems.append(f'Local-only artifact: {name}')
        if path.is_file() and any(pattern.search(path.read_bytes()) for pattern in SECRET_PATTERNS):
            problems.append(f'Possible credential in {name} (value suppressed)')
    if problems:
        print('\n'.join(problems))
        return 1
    print(f'Public-file check passed for {len(names)} files. No local-only artifacts or known token formats found.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
