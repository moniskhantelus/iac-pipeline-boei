#!/usr/bin/env python3
"""Refresh embedded runtimes; --check fails if any generated copy differs from source."""
import argparse
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"(?m)^([ ]*)(python3 - [^\n]+ <<'PY_CONTROL')\n(.*?)^\1PY_CONTROL\n", re.S)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = (ROOT / 'runtime/control.py').read_text().rstrip('\n') + '\n\n'
    compile(source, 'runtime/control.py', 'exec')
    changed = []
    copies = 0
    for path in sorted(list((ROOT / 'templates').rglob('template.yml')) + list((ROOT / 'iac').glob('*.yml'))):
        text = path.read_text()
        def replace(match):
            nonlocal copies
            copies += 1
            pad = match[1]
            return pad + match[2] + '\n' + ''.join(pad + line + '\n' for line in source.splitlines()) + pad + 'PY_CONTROL\n'
        result = PATTERN.sub(replace, text)
        if result != text:
            changed.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.write_text(result)
    if not copies:
        raise SystemExit('No embedded runtimes found')
    if args.check and changed:
        print('Stale generated runtime: ' + ', '.join(changed), file=sys.stderr)
        return 1
    print('%s embedded runtimes verified' % copies)
    return 0

if __name__ == '__main__':
    sys.exit(main())
