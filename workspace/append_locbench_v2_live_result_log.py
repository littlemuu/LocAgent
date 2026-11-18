from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_LOCBENCH_V2_LIVE_RESULT.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-13｜批准的 LocBench 两题修复版补测完成'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended LocBench repaired live retest result development log.')
else:
    print('Development log already contains this entry; unchanged.')
