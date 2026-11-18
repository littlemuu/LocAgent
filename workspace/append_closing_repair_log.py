from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_CLOSING_REPAIR.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜显式收尾控制与硬预算保护修复'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended explicit closing control repair and offline acceptance.')
else:
    print('Entry already present; unchanged.')
