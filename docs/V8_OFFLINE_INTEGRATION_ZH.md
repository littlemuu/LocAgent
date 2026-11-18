# v8 完整混合检索：OpenHands 离线接入验收

2026-11-16。阶段 A/B 已完成：旧优化方案的函数正文 BM25、精确 dense 余弦、实体最大块聚合、dense2/BM251 RRF60 及文件投影，已经通过新 `sdk_hybrid_v8` 接入实际 OpenHands SDK。40 项测试通过，端到端演示完成。向量为人工合成夹具，LLM 响应为脚本；这次证明接线和排序规则可用，不评价真实语义召回或模型定位质量。

新增真实 LLM 请求 0、embedding 请求 0、费用 0。没有读取 provider 密钥、使用数据库或消费既有六题授权。v7 原代码与封存结果保留。

## 运行入口

项目根目录：`/Users/xiaomu/Projects/LocAgent-OpenHands`。

```sh
cd /Users/xiaomu/Projects/LocAgent-OpenHands
./scripts/test_v8_offline.sh /private/tmp/locagent-v8-offline-check
```

输出目录必须不存在；首次失败立即退出，不自动重试。默认使用项目现有两个环境：SDK 环境 `workspace/.venv-openhands` 与检索环境 `legacy/locagent-demo/.venv`。二者仍是此前迁移留下的本机符号链接，没有安装或升级依赖。可用 `V8_SDK_PYTHON`、`V8_RETRIEVAL_PYTHON`、`V8_LEGACY_ROOT` 显式指定环境/旧代码位置。

验收产物：`workspace/verification/sdk-hybrid-v8-offline-v1/`。

- `acceptance.json`：总验收、40 项测试、v8 源码 SHA256。
- `core/summary.json`、`core/tests.log`：26 项检索/缓存/旧算法对齐检查。
- `sdk/summary.json`、`sdk/tests.log`：14 项实际 SDK、分页、预算和故障检查。
- `demo/acceptance.json`：端到端接受条件。
- `demo/sdk/contract.json`、`result.json`、`trace.jsonl`、`sdk-events/`：配置/快照/缓存绑定、实际工具分派、下一轮上下文及终答记录。
- `legacy-integrity.txt`：已有迁移文件及两份 v7 锁的完整性复核。

## 已接通的处理链

`OpenHands → locagent_retrieve → 会话分页缓存 → 隔离检索子进程 → 正文BM25 / dense → 实体聚合与加权RRF → 有界源码预览 → 下一轮SDK上下文 → read_file → finish`

OpenHands 仍是唯一会话控制循环。检索子进程不调用 LLM，也不执行被检索源码。`ProcessRetriever` 实现现有 `snapshot_id` 和 `retrieve(query) -> str` 接口，可直接交给现有 `ToolSession(snapshot, retriever=...)`，无需改写通用工具执行器或历史版本。

| 能力 | v8 实现 |
|---|---|
| 函数正文语料 | AST 函数/异步函数，含方法、嵌套函数、装饰器；按物理行切块，默认 max_chars=12000；输入是实体 ID、换行、源码 |
| BM25 | bm25s Lucene，k1=1.5、b=0.75，English stemming/stopwords，仅正分；覆盖完整函数正文 |
| dense | 校验并归一化给定缓存，计算精确余弦；本版仅接受 synthetic-fixture |
| 实体聚合 | 同一实体多块取最大分，先去重再排名 |
| 加权融合 | BM25 权重1、dense 权重2、RRF常数60；两臂完整排名参与，无预截断，最后取 top-k；同分按实体 ID 排序 |
| 文件排名 | 从完整实体排名按每个文件的最佳实体名次投影，单独保留 top-k 文件 |
| 精确路线 | 完整实体 ID、明确路径、完整限定名；不再使用 v6 符号组件重排覆盖自然语言融合结果 |
| 证据呈现 | 复用 v6 的预览实现，保留融合顺序；行号、省略说明、重叠抑制和 read_file 补读 |
| 模式审计 | requested/executed mode、来源分数和名次、融合分数、文件投影、预览范围、快照/语料/缓存/配置哈希 |
| 缓存与故障 | 同一查询分页复用结果；缓存缺查询默认停机；只有明确 fallback=body_bm25 才降级，文本和审计均标记 |
| 预算 | 共享现有工具调用/证据预算；离线脚本请求/响应大小检查；关闭调查后只能 finish |

算法参数和语料政策进入配置哈希及会话合同。缓存严格绑定快照、语料、文档成员、模型标识、维度与内容哈希。非有限/零向量、成员缺失或混入、错版本不允许降级掩盖；worker 超时或校验失败后失败状态保持，后续请求不重试。

## 与旧优化实验的对齐与明确差异

26 项核心测试中包含对旧 `offline_bailian_rrf.py` 纯排序函数的50组合成排名比较；公共语料范围内，装饰器、嵌套异步函数、CRLF和长行的块文本、范围及块序号与旧 `rag_offline.chunk_snapshot` 一致。文件投影使用完整实体顺序，避免先截取函数 top-k 导致文件候选丢失。

v8 输入是调用者已经明确选择的只读 Snapshot，纳入其中所有 Python 函数，不再叠加旧 `allowed()` 的文件名过滤。显式允许的隐藏 Python、settings/config 和测试函数不会静默被移除；非 Python 源码记录为排除项。BOM 只在 AST 解析视图去除，原始源码和物理行号保留。重复限定实体定义会明确报错。无函数语料的自然语言检索返回空，精确文件读取仍可工作。这是带独立身份的新语料政策，不宣称与历史 expanded50 的成员清单或向量 ID 完全相同。

本次复用了历史排序语义，并采用专门的绑定缓存执行离线精确余弦，没有引入旧 HTTP 服务、GraphLocalizer 循环或 PostgreSQL。当前每个新查询重建一次子进程内索引；同查询分页不重建。多查询索引驻留与大仓库性能优化尚未实现。

## 离线验证结果

- 26 项核心检查通过：正文词命中、正分/空候选、余弦归一化、实体最大块、RRF旧函数一致性、截断顺序、文件投影、缓存错绑/损坏、明确降级、精确路线、物理行及范围、预览排序和分页。
- 14 项 SDK 检查通过：实际工具分派、证据进入下一请求、源码补读、结构化终答、证据预算关闭、请求/响应大小限制、缺查询停机、超时无重试、worker身份/禁网状态校验、关闭工具不再检索。
- 独立端到端演示：3 次脚本化 SDK generate，1 次检索 worker，随后 read_file 与 finish；使用真实 SDK 1.62.0，不连接模型端点。
- 统一检查入口将测试发现和 SDK 导入也放入禁网上下文；最终核心套件、SDK 套件和演示的网络尝试均为0。首次调试时直接运行 unittest，曾观察到 LiteLLM 导入尝试下载公开价格表并 DNS 失败；已用该统一入口补齐导入阶段保护，最终验收未重现。该调试尝试没有题面/源码或模型请求。

禁网保护是 Python socket/API 层，适用于此次受检依赖，并非对任意恶意程序的操作系统级沙箱。worker 仅收到选定源码、配置和合成向量，环境变量白名单不包含凭证。SDK 请求大小记录的是离线序列化请求，不冒充真实 HTTP wire 计量。

## 代码导航

- `workspace/experiments/sdk_hybrid_v8/config.py`：固定模式、参数与算法身份。
- `corpus.py`、`ranking.py`、`vectors.py`：分块、排序/文件投影、绑定向量缓存。
- `retriever.py`：精确/自然语言分流、融合预览、降级与来源审计。
- `bridge.py`、`worker.py`：只读 IPC、独立依赖环境、超时与失败状态。
- `sdk_adapter.py`：离线专用 SDK 会话与结构化终答；没有 live/凭证参数。
- `demo.py`、`offline_checks.py`、`workspace/tests_v8/`：合成演示和可复现验收。

## 后续路线

1. **真实向量资产与格式**：先找回原 manifest、输入/响应与向量；逐项核验文本、角色、模型、维度和成员范围。新语料政策导致缓存身份不同，需要显式转换和来源绑定，不能直接改 synthetic 标签复用。
2. **受控查询编码**：在禁网检索 worker 外设置独立编码边界；单独落实供应商、数据范围、请求/费用上限、超时与无自动重试。模型自由生成的查询无法由当前固定合成缓存覆盖。
3. **真实对照**：固定 SDK 循环、自检提示、语料、预览及证据预算，对比正文 BM25 与 BM25+dense 加权 RRF。先验冻结样本/重复与分项成本，分别测初始检索召回和 Agent 终答。当前六题成绩不变，也没有新增 v8 Recall@5。
4. **后续能力**：图邻接探索、候选状态追踪/自主补读，以及跨查询索引复用分别实现和消融，避免同时改变过多变量。
