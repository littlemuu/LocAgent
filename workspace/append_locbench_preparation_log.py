from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_LOCBENCH_PREPARATION.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-13｜LocBench 两道已曝光开发题接入 OpenHands，离线验收'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended LocBench offline preparation development log.')
else:
    print('Development log already contains this entry; unchanged.')
