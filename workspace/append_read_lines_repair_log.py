from pathlib import Path

entry = Path(__file__).with_name('DEVELOPMENT_LOG_READ_LINES_REPAIR.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-13｜共享按行读取修复与检索选择假说：仅离线'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended shared line reader repair development log.')
else:
    print('Development log already contains this entry; unchanged.')
