from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_SQLGLOT_READ_LIVE_RESULT.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-13｜批准的 SQLGlot 单题读取验证完成'
if marker not in target.read_text():
    with target.open('a') as stream:stream.write(entry)
    print('Appended SQLGlot approved live validation result log.')
else:print('Entry already present; unchanged.')
