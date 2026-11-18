from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_LOCBENCH_OFFLINE_DIAGNOSIS.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-13｜LocBench 两题轨迹、检索与参考映射离线诊断'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended LocBench offline diagnosis development log.')
else:
    print('Development log already contains this entry; unchanged.')
