"""Append this completed offline investigation to the existing project log only."""
import fcntl
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
MARKER = '## 2026-11-14｜batch134 与 OpenHands 引擎差异离线核验'
ENTRY = '''

## 2026-11-14｜batch134 与 OpenHands 引擎差异离线核验

按小目“来确认差异影响吧”的要求，复算 batch134 runtime-engine 159 文件聚合 2222b6bac8ac393a7aeb29e571edefe351146320e62384627cecdaeba9a3f196，当前 OpenHands 所用 LocAgent 146 文件聚合 975172d7d0a1590be5033779d1349462fa5cba497b3b0554fce815a1f5a0d944，均与冻结记录一致。更正此前计数：12 个共有文件内容差异、1 个当前独有 requirements-demo-test.txt、14 个 batch134 独有文件，并非 13 个共有文件差异。逐项分类与 diff 已保存。

当前 OpenHands 每次从源码构图并建立实体 ID BM25，不加载旧 graph.pkl 或正文 corpus。两道已曝光题全部 bundle 文件先验证哈希，再在临时隔离进程做受限图读取/本地查询；没有改正常版本门禁。正常 load_manifest 在 batch134 接受两个旧 manifest，在当前引擎均拒绝 Engine changed。实体/正文索引的小范围格式兼容，不等于生产授权或全批兼容。

同一 Python 3.12 环境、同一冻结 Python 源码下，batch134 比当前新建图多 SQLGlot 48、Loguru 38 个构造函数相关实体，共有节点属性一致。5 个已有查询在两引擎×新建/归档图四组合的 20 次本地检索中原始输出相同；正文 BM25 两索引也可加载，所测查询结果相同。两个已曝光参考函数名称、行号与正文映射一致。人工样例则复现构造函数及 pkg.github 目录覆盖导致的检索差异；因此不能推断所有检索结果相同。

130 题仅查 manifest 元数据与文件 stat，发现 7 题有 14 个隐藏 Python 路径，而当前 Snapshot 拒绝隐藏路径。人工 CRLF 样例在两套图构建器下均被当前逐字校验拒绝，未放宽检查。归档 prepare 另有根节点 /→. 归一，旧构建 Python 3.10 与当前 3.12 的 except* 解析差异对应 Loguru 两个测试函数，未复跑旧容器。旧路径 replace 的相对路径反例也可复现。未查看未曝光题的题面/标签/正文调参。

建议复用固定源码及来源证据，新建 OpenHands 适配清单并显式固定源码范围、解释器/依赖、引擎、索引及评分；先处理覆盖和换行保真，再逐题技术门禁，不能去掉引擎哈希校验或把旧 130 technical-ready 直接升级为当前通过。只完成小范围离线检查，没有全批重建或引擎改动。

验证：6 个隔离重建/查询 worker、4 次正常 manifest 门禁检查；23 项结果断言通过，1,728 个既有受保护文件哈希未变。真实模型请求 0、费用 0；没有读取密钥或 .env，没有向外发送数据、安装依赖或执行目标仓库代码。Python 网络/模型防护不声称为 OS 级沙箱。

报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/ENGINE_COMPATIBILITY_REPORT.md。
证据与验收：/Users/xiaomu/Documents/Codex/2026-11-12/task/verification/engine-compatibility-v1/，包括 acceptance.json、preflight.json、manifest-gate-probe.json、manifest-metadata-audit.json、exposed-label-mapping-check.json 及逐文件 diff。
'''


def main():
    assert json.loads((ROOT / 'verification/engine-compatibility-v1/acceptance.json').read_text())['status'] == 'passed'
    with LOG.open('r+b') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        before = stream.read()
        assert MARKER.encode() not in before, 'entry_already_present'
        addition = ENTRY.encode()
        stream.seek(0, os.SEEK_END)
        stream.write(addition)
        stream.flush()
        os.fsync(stream.fileno())
        stream.seek(0)
        after = stream.read()
        assert after == before + addition
    receipt = {'log': str(LOG), 'before_sha256': hashlib.sha256(before).hexdigest(),
               'after_sha256': hashlib.sha256(after).hexdigest(), 'appended_bytes': len(addition),
               'previous_contents_preserved': True}
    with (ROOT / 'verification/engine-compatibility-v1/development-log-receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
