from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_RETRIEVAL_CHOICE.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12 北京时间｜自主检索未选择的离线分析与说明修订'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended offline retrieval-choice review.')
else:
    print('Entry already present; unchanged.')
