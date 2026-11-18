from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_RETRIEVAL_CHOICE_OFFLINE.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-13｜工具说明配对离线试跑完成'
if marker not in target.read_text():
    with target.open('a') as stream:stream.write(entry)
    print('Appended offline retrieval-description pair trial log.')
else:print('Entry already present; unchanged.')
