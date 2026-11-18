from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_LOCAL_ENV.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜复用本地 .env 与显式密钥加载'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended local env setup and verification.')
else:
    print('Entry already present; unchanged.')
