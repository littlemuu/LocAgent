from pathlib import Path
entry = Path(__file__).with_name('DEVELOPMENT_LOG_SQLGLOT_READ_VALIDATION_READY.md').read_text()
target = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
marker = '## 2026-11-13｜SQLGlot 共用读取修复后的单题验证准备'
if marker not in target.read_text():
    with target.open('a') as stream:
        stream.write(entry)
    print('Appended SQLGlot read validation preparation development log.')
else:
    print('Development log already contains this entry; unchanged.')
