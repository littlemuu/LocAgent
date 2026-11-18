# v8 真实向量资产盘点与旧电脑取回清单

2026-11-16。当前结论：**本机尚未找到可核验并复用的历史真实向量；用户已确认原始资产仍在旧电脑，将打包传回。** 已找到历史模型契约、清单哈希、执行/独立复核代码和报告，可以据此验证原件。本轮没有调用任何模型或 embedding API、读取密钥、启动数据库、重跑历史账本或改动 v8。

## 现在已经核实什么

- 检查 Projects、Documents、Downloads、Desktop 的859,057个文件路径，包含 Git 忽略文件；排除 Git 内部、安装环境、node_modules、.tools、凭据配置等。没有发现 `outputs/bailian*` 原始资产路径。此范围不等于整台电脑、其他设备或云端的穷尽搜索。
- 在6个相关检出/安装目录核查6项关键资产，共36项存在性检查，均缺失；并搜索 JSON/JSONL 中的向量、模型和冻结文档字段，没有找到候选真实缓存。
- 检查 `locagent-local-install-20261107-source.zip` 和 `locagent-demo-20261108-source.zip`，分别327/346成员，不含原始百炼证据。
- 本机同名 `.npy` 索引候选是 BM25 的 `data/indices/indptr.csc.index.npy`，不能当作1024维语义向量。
- 2026-10-30迁移记录明确写明：历史 outputs、下载源码缓存、索引、原始模型响应和旧数据库未迁移。当前缺失发生在 v8 之前；不能据此判断旧电脑数据丢失。
- 旧实验资产位置已经由用户确认为旧电脑的 `/home/lenovo/projects/LocAgent-rag-preview/`。

## 资产分层与复用判断

| 资产 | 历史记录 | 本机状态 | 收到原件后的用途/限制 |
|---|---|---|---|
| expanded50真实向量 | 9,814个唯一文档输入＋50个查询；49个commit、9个仓库 | 原始向量、冻结manifest、原始响应/事件链均未找到 | 优先恢复；逐条验证后用于真实向量离线回放和候选输入匹配 |
| 32块/10查询小实验 | itsdangerous固定commit；其中2个文档向量复用A/B单输入 | manifest、5份来源body/binding及SQLite账本未找到 | 可做较小的真实向量接线检查；A/B不能再额外计入32个文档 |
| 更早诊断/失败批次 | 有unknown和历史raw缺失记录 | 仅存报告和代码 | 不因拿到派生safe.json就认定可复用；缺原始显式索引绑定的旧批次不能按数组顺序猜映射 |
| 算法、契约、报告 | 模型/角色/预处理/分块/加权融合规则、清单SHA256 | 可用 | 作为核验依据；报告里的数量与指标不是已恢复向量的证明 |
| 当前v8合成缓存 | synthetic-fixture、2维演示 | 已验证 | 仅用于协议/离线测试，不能改标签充当真实向量 |

**当前六题的仓库覆盖不匹配。** expanded50为 boltons、more-itertools、click、markupsafe、packaging、attrs、humanize、python-dotenv、cachetools；旧小实验为 itsdangerous。六题来自 luigi、sqlglot、xcdat，仓库级交集为0/3。因此恢复旧资产能让我们验证“真实向量接入链路”，但不能据此宣称六题已有文档向量。跨仓库是否偶有完全相同的路径/符号/源码输入，仍须拿到manifest后逐项哈希比对，不能仅凭仓库名称判为绝对无交集。

模型动态生成的查询也不能直接复用旧50/10条固定查询缓存；只有完整UTF-8查询文本、角色、instruct及模型契约均相同才可能命中。

## 旧电脑怎么打包

配套脚本：`pack_locagent_vectors.py`。复制到旧电脑后，在 Linux/WSL 中运行：

```sh
python3 pack_locagent_vectors.py \
  --root /home/lenovo/projects/LocAgent-rag-preview \
  --output /tmp/locagent-vector-evidence-20261116.zip
```

将生成的 ZIP 和终端输出的 SHA256 一并带回即可。输出文件必须不存在，并位于项目目录外。脚本只读文件、按原字节打包并生成逐文件哈希，不导入项目代码、不访问网络、不执行prepare/run/resume、不生成向量、不改源文件。没有找到历史 `outputs/bailian*` 时会明确报错，不生成空资产包。

自动收集 `outputs/bailian*` 及配套百炼契约、分块器、expanded/独立审计脚本、历史报告和依赖文件；不包含项目根目录 `.env`、provider.local.json、密钥文件或虚拟环境。符号链接会拒绝，避免意外遍历其他位置。包内 `TRANSFER_MANIFEST.json` 列出缺项、逐文件字节数/哈希，以及expanded清单是否匹配历史固定哈希。这个传输清单证明传输内容一致，尚不等于真实向量来源核验通过。

脚本已通过5项本地夹具检查：字节与哈希一致/源文件不变、凭据配置与无关文件排除、符号链接拒绝、已有输出不覆盖、缺历史目录不生成包。

### 手动打包时必须保留的目录

以下均相对旧项目根目录，优先完整保留相对结构：

1. `outputs/bailian-expanded50-20261016/`：尤其 `frozen/manifest.json`、`archives/`、`snapshots/`、`source/`，用于核对输入文本、49个commit的源码和成员映射。
2. `outputs/bailian-expanded-budget-runs/bailian-expanded50-78e24794-cap2-20261016-r01/`：整个目录，含run、原始body、原事件、continuation授权/事件/body。原403失败也保留，不能只挑成功文件。
3. `outputs/bailian-expanded50-resumed-evaluation-20261016-r01/` 与 `outputs/bailian-expanded50-live-evaluation-20261016-r01/`：来源清单、账本审计及结果。
4. `outputs/bailian-expanded-live-preflight-20261016/`、`outputs/bailian-expanded-resume-preflight-20261016/`、`outputs/bailian-expanded50-independent-review-20261016/`：若存在则一并保留。
5. `outputs/bailian-retrieval-20261016/`、`outputs/bailian-mapping-controls-20261015/`、`outputs/bailian-rrf-offline-20261016/` 及同前缀独立manifest：用于32/10小实验。其他 `outputs/bailian*` 历史目录也一并保留，避免漏掉保护清单引用的证据。

若Linux目录部分缺失，另一个有据可查的副本位置是旧Windows `/mnt/c/Users/Lenovo/Documents/Codex/2026-10-13/task/`：冻结脚本曾导出 `bailian-expanded50-manifest.json`、queries.csv、audit.json。它们可补清单/摘要，但不应假设包含所有原始向量。没有必要为了打包重新执行实验。

## 收到包后的离线核验顺序

1. **传输完整性**：检查ZIP成员路径、文件类型和逐文件SHA256；只在新的恢复目录解包，不覆盖历史或v8目录。
2. **固定清单身份**：expanded manifest应为 `78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b`；32/10实验manifest应为 `a6a0abb4f12cc6d45fce36a89a384ccd0d92175b94c0246abc9f9b3e14ebf39f`。哈希不匹配则隔离，不直接复用。
3. **真实响应与映射**：expanded前490成功批次读 `body-000000.bin` 至 `body-000489.bin`；其后128成功批次读 `continuation-body-000490.bin` 至 `continuation-body-000617.bin`。原 `body-000490.bin` 是403失败，不是可复用向量。逐项重算请求/响应哈希、事件链、HTTP状态、显式index/text_index、维度、有限非零范数及角色成员覆盖。
4. **数量与来源**：历史应有618个成功唯一批次、619个物理attempt（含保留的失败），覆盖9,814 document＋50 query。数量只在原件核验后确认；不修改历史unknown状态或费用。
5. **源码与缓存契约**：从固定归档重建函数块，核对源码/块文本、模型 `qwen3.7-text-embedding-flash`、1024维、endpoint、角色、query instruct、UTF-8预处理与max_chars=12000。对当前v8语料做完整输入匹配，输出可复用/不匹配/缺来源的明细。
6. **迁入v8前兼容处理**：v8现在仅允许synthetic缓存，真实缓存需要单独格式和来源校验；不能改个标签绕过。旧语料含重载/同限定名定义，而v8当前会拒绝重复实体定义，需明确兼容策略后再接入。旧chunk ID与v8 ID不同，可基于已验证的完整输入和契约建立显式映射，不按名称盲配。
7. **真实向量离线回放**：先在已恢复的小实验或expanded固定快照跑，无需新增embedding。六题缺失的文档/新查询另列清单，保持“不调用付费服务”的当前约束。

这轮交付的是**本机盘点、历史来源定位和取回工具**；真实向量内容核验、精确复用数量和实际导入，等旧电脑原件到齐后继续。
