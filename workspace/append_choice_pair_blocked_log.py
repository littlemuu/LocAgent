from pathlib import Path
entry=Path(__file__).with_name('DEVELOPMENT_LOG_CHOICE_PAIR_LIVE_BLOCKED.md').read_text()
target=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker='## 2026-11-13｜真实工具说明配对准备完成，自动审核阻止启动'
if marker not in target.read_text():
    with target.open('a') as stream:stream.write(entry)
    print('Appended blocked pair launch preparation log.')
else:print('Entry already present; unchanged.')
