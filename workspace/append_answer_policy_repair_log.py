from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_ANSWER_POLICY_REPAIR.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-12｜取消终答字符硬限制与异常证据报告修复'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended answer policy repair and offline verification development log.')
else:
    print('Development log already contains this repair; unchanged.')
