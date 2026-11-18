"""Append the completed BOM fix and explicit v4 validation provenance."""
import fcntl,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'engine_adaptation/v4'
LOG=Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/DEVELOPMENT_LOG.md')
def main():
 a=json.loads((OUT/'acceptance.json').read_text());assert a['status']=='passed' and a['technical_ready']==130
 marker='## 2026-11-14｜MSAL UTF-8 BOM 修复与 v4 的 130 题技术验收'
 entry=f'''

{marker}

按小目后续授权继续离线修复 MSAL 407/454。根因是 ast.parse(str) 不把解码后的开头 U+FEFF 视为编码签名。v4 仅在 AST/import 解析及实体提取的解析视图中去掉一个初始 U+FEFF；适配器采用相同规则。原 Snapshot、文件节点、SHA256、IPC 和 read_file 内容完整保留 BOM；非 BOM 文本、CRLF 和行号不变，内部 U+FEFF 不删，重复或非首位 BOM 仍拒绝。

新引擎副本 hash：{a['engine_hash']}。相对 v3 只改图构建器；harness 仅 readonly_agent/locagent.py 修改，修改前原文已备份在新目录。没有修改原引擎、v3 产物或旧授权。

两道 MSAL 题重新静态构图与建索引，均43个 Python 文件、4个 BOM 文件；407新图508节点，454新图525节点；每题4个 BOM 文件含34个类/函数实体，原始文件字节和 AST 实体绑定通过。没有运行目标 setup.py、模块或测试。先通过含首行 BOM/CRLF/中文、内部 U+FEFF 和 import 的隔离组合样例及两题门禁，再复验其他128题。

128题确认无开头 BOM，新增解析视图对这些源码为恒等变换。逐题验证旧索引哈希与源码快照；在新适配器下重新验证 JSON 图的文件/实体覆盖与精确正文，重建内存实体 BM25，并比较持久化索引全部 corpus 文本及固定 __init__ 查询返回 ID；隐藏 Python 路径再次精确读取。没有重算这些题的图边，保留 v3 build 来源。最终130/130题技术通过：2题重建、128题复验复用，不能说130题全部重建。

45个单元测试、4个现有集成测试通过；先前构造函数/隐藏路径/CRLF/伪造正文与缺实体拒绝/IPC/行号回归通过。新增测试覆盖一个初始BOM、非首位/重复BOM拒绝、BOM首行函数与Unicode、内部字符保留、非BOM与原AST一致。旧1280个索引产物哈希复核未变，v3的2题失败与128题通过记录保持历史原貌。

最新清单：/Users/xiaomu/Documents/Codex/2026-11-12/task/engine_adaptation/v4/adapted-manifest.json，分别记录 index_build_engine_hash 与 validated_engine_hash；验收 acceptance.json、逐题 validation/。报告：/Users/xiaomu/Documents/Codex/2026-11-12/task/BOM_ADAPTATION_REPORT.md。

仅技术验收完成。语义、曝光、评分仍pending，未宣称独立测试集或正式评测。没有真实模型请求/费用、密钥/.env读取、依赖安装、目标代码执行或数据外发。真实模型入口未运行或切换，缓存尚未接入实时运行器，旧授权未换绑；未来执行需选择新版本并重新冻结。Python防护不声称OS沙箱。
'''
 with LOG.open('r+b') as f:
  fcntl.flock(f,fcntl.LOCK_EX);before=f.read();assert marker.encode() not in before
  f.seek(0,os.SEEK_END);f.write(entry.encode());f.flush();os.fsync(f.fileno());f.seek(0);after=f.read()
  assert after==before+entry.encode()
 with (OUT/'development-log-receipt.json').open('x') as f:
  json.dump({'before':hashlib.sha256(before).hexdigest(),'after':hashlib.sha256(after).hexdigest(),
   'append_bytes':len(entry.encode()),'previous_content_preserved':True},f,indent=2)
 print('Appended BOM fix and 130-case technical validation; original log preserved.')
if __name__=='__main__':main()
