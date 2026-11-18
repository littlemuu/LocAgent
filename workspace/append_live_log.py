from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_LIVE.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 UTC｜锁定的真实传输、一次性授权与离线验收'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended locked transport and offline acceptance entry.')
else:
    print('Entry already present; unchanged.')
