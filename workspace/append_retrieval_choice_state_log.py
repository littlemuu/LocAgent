from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_RETRIEVAL_CHOICE_STATE.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-13｜未选检索的状态对照与正例核验'
if marker not in target.read_text():
    with target.open('a') as stream:stream.write(entry)
    print('Appended retrieval choice state comparison log.')
else:print('Entry already present; unchanged.')
