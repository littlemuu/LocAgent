"""Append completed adaptation stages, including failures, without replacing history."""
import fcntl,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'engine_adaptation/v3'
LOG=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
def main():
 a=json.loads((OUT/'acceptance.json').read_text())
 marker='## 2026-11-14｜130 题源码适配：构造函数与保真读取'
 entry=f'''

{marker}

按小目指定顺序离线实施。原图显式跳过同步 __init__，旧设计不满足精确函数定位覆盖要求。建立当前引擎的隔离副本，移植 batch134 图构建器的构造函数/嵌套实体、目录组件与软链接处理，保留禁止新增构造函数参与后缀模糊调用解析的保护；没有迁移旧 Agent 循环。图文件读写改为 UTF-8 原始换行，CRLF/Unicode 保留，继续校验原始文件与精确 AST 正文。新增文件/实体覆盖门禁，不能静默漏建。

## 2026-11-14｜130 题源码适配：隐藏路径端到端修复

Snapshot 增加独立逐文件 hidden_python_paths，默认仍拒绝隐藏路径；只容许源码清单内显式 .py，管理/凭据目录、软链接及越界继续拒绝。策略绑定计划并传入隔离 IPC。第一版建图后端到端查询发现 _entity_input 会去掉 .ci 开头点；v2 保留点后，真实题又发现 get_entity_contents 默认排除 test 名称文件。v3 修正明确指定的已入图实体读取，仍保留关键词 BM25 的测试文件过滤。前两版结果、失败和 superseded 记录全部保留，没有将建图成功冒充检索通过。

第三版组合边界回测通过构造/嵌套实体、带点普通目录、无错误构造调用边、CRLF、隐藏路径 IPC、伪造正文/漏建实体/漏建文件拒绝和行号；真实 7 题的 14 个隐藏路径逐个精确读取成功。41 个单元测试、4 个现有集成测试通过。一个旧隔离测试手工构造的不完整图现按新门禁拒绝，已为其补全真实函数节点以保持隔离测试意图，另有缺实体负向检查。

## 2026-11-14｜130 题源码适配：新冻结计划与全量技术检查

最终引擎哈希 {a['engine_hash']}；新副本146文件，仅图构建和 repo_ops 两文件与原当前引擎不同，原两引擎均未修改。先人工样例、已曝光 SQLGlot/Loguru 两题及隐藏路径7题，全部通过后扩展剩余121题；每题新临时源码/进程，最多3并发，CPU90秒/墙钟120秒。最终130题：{a['ready']}题技术通过，{len(a['blocked'])}题阻塞。失败不自动重跑，不算题目无效或评测零分。实际阻塞ID：{', '.join(a['blocked']) or '无'}。

追加只读语法探针定位 MSAL 四个文件的 UTF-8 BOM 被字符串 AST 解析拒绝；这是原先未显露的编码适配缺口，尚未修复，不能靠删文件或放宽字节校验过关。语义、曝光与评分映射仍 pending。130题索引准备不等于130题可独立评测。

产物在 /Users/xiaomu/Documents/Codex/2026-11-12/task/engine_adaptation/v3：manifest/plans 绑定父 source_id、提交、源码与隐藏白名单、引擎和 harness；成功项含 JSON 图与数值 BM25 索引、哈希证明。失败目录保留。人工/两题的持久化索引加载回测通过。全部22897个来源 Python 文件引用的路径检查无越界或软链接。

现有实时接口仍从源码构图，未把缓存索引接入付费入口；新实验需选择新引擎并重新冻结，旧授权未换绑，哈希校验未关闭。旧受保护材料中只6个预期 harness 源文件变化，其余{a['unchanged_historical_files']}个哈希不变，旧索引、账本、模型结果保留。真实模型调用0、费用0；未读取密钥/.env、安装依赖、执行目标仓库代码或外发数据。Python 防护非 OS 沙箱。

完整报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/SOURCE_ADAPTATION_REPORT.md；逐题状态见 engine_adaptation/v3/adapted-manifest.json 和 full-validation-results.json，验收见 acceptance.json。
'''
 with LOG.open('r+b') as f:
  fcntl.flock(f,fcntl.LOCK_EX);before=f.read();assert marker.encode() not in before
  f.seek(0,os.SEEK_END);f.write(entry.encode());f.flush();os.fsync(f.fileno());f.seek(0);after=f.read()
  assert after==before+entry.encode()
 with (OUT/'development-log-receipt.json').open('x') as f:
  json.dump({'before':hashlib.sha256(before).hexdigest(),'after':hashlib.sha256(after).hexdigest(),
   'append_bytes':len(entry.encode()),'previous_content_preserved':True},f,indent=2)
 print('Appended three completed adaptation stages; prior log content preserved.')
if __name__=='__main__':main()
