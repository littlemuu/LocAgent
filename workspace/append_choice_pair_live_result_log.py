from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_CHOICE_PAIR_LIVE_RESULT.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-13｜明确批准的工具说明真实配对首请求后停止'
if marker not in target.read_text():
    with target.open('a') as stream:stream.write(entry)
    print('Appended actual pair stop and diagnosis log.')
else:print('Entry already present; unchanged.')
