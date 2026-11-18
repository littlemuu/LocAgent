"""Append this reviewed entry once, preserving the existing development log."""
from pathlib import Path

source = Path(__file__).with_name('DEVELOPMENT_LOG_ENTRY.md')
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
entry = source.read_text()
marker = '## 2026-11-12 UTC｜只读工具独立化，并验证 OpenHands SDK 底座'
if marker in target.read_text():
    print('Entry already present; unchanged.')
else:
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended reviewed development entry.')
