from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_LOCBENCH_BATCH_READY.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-13｜LocBench 两题真实批量入口完成离线授权与预算验收'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended LocBench batch offline acceptance development log.')
else:
    print('Development log already contains this entry; unchanged.')
