# LocAgent 预览分支交接：2026-10-17

工作目录 `/home/lenovo/projects/LocAgent-rag-preview`，分支 `work/rag-offline-preview`；整理前 HEAD `657aca1258547d43abae73aee01812e19f13b711`。本轮从 35 个既有未跟踪文件开始，没有其他已跟踪文件修改。按准备、预算与恢复、文档整理分批本地提交，不 push、合并或部署。原学习工作区不变。

## 当前能做什么

| 路径 | 已验证范围 | 不能据此声称 |
|---|---|---|
| demo-v1 / prepared + fake provider | 原图工具、API 请求边界、任务执行与恢复的离线回归；历史数据库验收另见各阶段报告 | fake 输出能评价模型定位质量 |
| public GitHub + BM25 | HTTPS URL 校验、固定 commit、后台静态准备、并发缓存发布、持久任务和查询；2026-10-15 一次真实 API→worker→DeepSeek→结果成功 | 所有公开仓库均安全或当前版本已经重新跑过真实服务 |
| RAG / pgvector | 离线检索原语与独立 pgvector 实现、既有隔离验收 | dense/hybrid 已接入公开 HTTP 任务 |
| expanded50 | 9 仓库、49 个 repo/commit 快照、50 个 issue 标题，完整 embedding 向量及冻结三臂检索结果，独立离线复核 | 50 题完整 agent 定位准确率、无污染盲测或统计显著性 |

公开仓库是非可信输入，不执行安装脚本、测试或项目代码。下载、路径、符号链接、大小和解析边界参见 [公开仓库设计](PUBLIC_REPOSITORY_PREVIEW.md)。Python 子进程和 Python socket guard 都不是完整 OS 沙箱；公网部署、多租户鉴权与全面资源隔离不在已交付范围。

## 真实服务证据与版本差异

[单题验收](PUBLIC_SINGLE_SMOKE_ACCEPTANCE.md)记录了公开 `pallets/itsdangerous`，固定 commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`，问题为 “Where does the library reject an expired signed value when a maximum age is supplied?”。
任务 `40b536f0-15e6-4bae-80a8-4bc305c47339` completed / success，3 次 HTTP 200，全部 settled，usage 标价核算 0.031734 元，reserved=0。返回 `TimestampSigner.unsign` 和 `validate`，同时返回了较宽的文件集合。原失败静态任务零模型调用，记录保留。

本轮只读比较实际使用源清单 `prepared-287672318b943a8b8220861db037c9cf03c655e48b56b06dd9683b940230cdbe.json`：当前完整 engine 集合新增 20 项、修改 3 项（`public_repo.py`、`rag_graph_adapter.py`、`rag_offline.py`），没有删除项。**历史成功属实；当前代码精确版本的真实服务验收尚缺。** 清单/授权必须拒绝旧绑定，不能为复用历史结果绕过哈希检查。

如果父对话决定补这一版本验收，最小方案沿用同一公开仓库、固定 commit 和上述问题，使用独立的新静态准备、源清单、授权和账本，保持旧证据不变。候选接收方为 `https://api.deepseek.com/chat/completions`，候选模型 `deepseek-flash`，最多 3 次请求、每次输出最多 1024 tokens、任务 300 秒、一次 attempt、提议预算上限 7 元。外发数据只有公开问题、检索到的公开源码、工具历史与提示词。上述为历史参数的待确认提案，模型可用性、费率、上下文上限和预算需届时重新核对，不构成当前授权。

命令模板在 [single-task runbook](PUBLIC_SINGLE_SMOKE_RUNBOOK.md)：`python -B -m locagent_service.public_authorization plan --source "$SOURCE_ID" --provider-config "$NEW_PRIVATE_CONFIG" --output "$NEW_PLAN"` 只生成待审计划；源来自新的静态 API 任务。正式 authorize 和 live POST 须等父对话确认单题、接收方、模型、预算与计划哈希。须替换旧 runbook 的日期、端口、schema、目录与资源名并检查占用；不照抄已消费授权、不重启原 demo。本轮未启动任何服务或真实请求。

## 检索结果与预算

[完整续跑结果](BAILIAN_EXPANDED50_RESUME_RESULT.md)、[独立复核](BAILIAN_EXPANDED50_INDEPENDENT_REVIEW.md)为最终记录。冻结 manifest SHA256 为 `78e24794a3e91bd0ba4ae8a54845e360cfd2add3b8b6feb8a49734b3c4ad555b`，没有改样本、gold、分块或参数。

| 方法 | 函数 Recall@5，n=30 | 文件 Recall@5，n=50 |
|---|---:|---:|
| BM25 | 52.22% | 83.73% |
| dense | 55.56% | 88.13% |
| RRF60，dense2/BM251 | 64.44% | 90.47% |

20 题 partial/NA 不进入函数主分母；gold 是修复补丁重叠代理。dense 的 @1 更好，RRF 的 @5 更好，不能概括混合在所有 K 上更优。独立复核的 150 份函数排名和 150 份文件排名完全一致，精确分数与浮点指标最大误差约 1.11e-16。

最终 619 次物理 attempt = 618 成功 + 1 原始 unknown；只对原失败批次按明确授权重试一次。9814 文档向量与 50 查询向量完整。成功 usage 核算 0.227484 元，原 unknown 0.262144 元保留，本 run 保守上界 0.489628 元；不是控制台账单。旧预算和此前 1.277952 元历史占用未重置。已完成的真实 CLI 和报告生成脚本均不应直接重跑，后者拒绝覆盖原证据。

## 本地复核入口

使用已有 CPU 环境，当前目录为预览工作区；不安装新依赖。原 `.venv` 可通过 PYTHON 指向，示例：

```sh
PYTHON=/home/lenovo/projects/LocAgent/.venv/bin/python
# 只读原始预算提案（不是当前余额）：不读取凭据、不发送请求、不修改账本。
"$PYTHON" -B scripts/preview_expanded_budget.py
# 离线单测：现有归档必需；不加 --postgres 或 --compose。
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  PYTHON="$PYTHON" sh scripts/check_local.sh
```

代理仅在上述命令环境移除；没有修改全局设置。纯单测不替代数据库/进程集成验收。部分 expanded50/gate/resume 测试依赖 ignored 的冻结样本和初次审计；新 clone 没有这些本地归档时，不能声称可完整重现。缺文件应报告，不应重新下载或生成付费向量来让测试通过。

代码清单：`scripts/prepare_expanded_subset.py`、`prepare_expanded50.py`、`freeze_expanded50.py` 为静态准备与冻结；`offline_bailian_rrf.py`、`score_expanded_bm25.py` 为检索；`locagent_service/bailian_expanded_runner.py`、`bailian_expanded_transport.py`、`bailian_expanded_resume.py` 为固定实验的预算、传输和恢复；`evaluate_expanded_live.py`、`evaluate_expanded_resumed.py` 与 `independent_expanded50_review.py` 为证据审计和评分。这些是固定历史实验工具，不是通用多租户授权服务；显式 approval ID 不是秘密或访问控制凭据。

历史 docs 中“未授权”“无 commit”等描述对应各自日期，不覆盖本轮本地提交授权。保留其时间顺序，不修改历史结论。冻结源码也保留原字节，避免使审计绑定失效。

## 本轮检查与剩余工作

本轮测试统计和提交前复核结果见下方追加记录。证据位于 ignored 的 `outputs/closeout-20261017/`；不提交原始响应、缓存、数据、账本、私有配置或密钥。密钥模式扫描只报告路径/类别，不输出匹配内容，不能替代人工审查。

剩余工作：当前精确版本的一题真实服务验收待父对话决定；dense/hybrid 接入 HTTP、完整 agent 配对评测、公网部署安全隔离尚未实现；原 unknown 的实际账单核销待人工查账。本轮不调用模型、不重放历史 paid ledger，不运行 PostgreSQL/Compose/公网验证。

### 最终离线记录

完整 unittest discovery：691 项，失败 0、错误 0、跳过 17，通过。 使用当前既有 CPU venv；额外封锁 Python INET 连接，所有模型路径仅 fake/mock。覆盖新 expanded 及原 demo/prepared/public、授权、预算、故障恢复回归。该结论不包括真实数据库或服务重启验收。

保护清单 3140 个文件复核哈希不变（独立复核所绑定历史证据、35 个既有新增文件以及原学习 README）。 `preview_expanded_budget.py` 通过，返回 dry-run、network_calls=0、writes=0；其 618 请求和 3.277952 元合计是假设新 cap 的原始计划展示，不是完成续跑后的当前余额，当前账目以上文最终审计为准。

`git diff --check` 与每批 staged diff 检查通过；35 个候选文件密钥模式扫描零发现，人工确认提交集合只有代码、测试、规则与文档。`.env.bailian.local`、`runtime.json`、`outputs/` 命中 ignore。未运行：真实模型/embedding、重新下载、数据库/Compose、当前版本真实单题与公网验证。

### 2026-10-17 pgvector 实际补跑：未通过

此前全量 discovery 的 17 项数据库跳过现已单独实际执行：**16 通过、1 错误、0 失败断言、0 跳过**。结合先前 674 项通过，当前 691 个用例的最新已执行结果为 **690 通过、1 错误**；不能标记整套验收通过。历史日志保留，不覆盖此前跳过记录。

运行前核验容器 `locagent-vector-acceptance-20261015` 为 exited，55441 无监听；image SHA256 为 `7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a`，仅映射 `127.0.0.1:55441→5432`，卷为 `locagent-vector-acceptance-20261015-data`。启动后仅连接既定 DSN `postgresql://postgres@127.0.0.1:55441/vector_acceptance`，核验数据库及用户、PostgreSQL 16.15、public.vector 0.8.7，均符合预期。没有拉镜像、安装扩展、改认证或网络配置。

实际由本地协调脚本设置上述 `LOCAGENT_VECTOR_TEST_DSN`，调用 unittest discovery（pattern=`test_rag_postgres_integration.py`）；与以下测试入口等价：

```sh
LOCAGENT_VECTOR_TEST_DSN=postgresql://postgres@127.0.0.1:55441/vector_acceptance \
  /home/lenovo/projects/LocAgent/.venv/bin/python -B -m unittest discover \
  -s tests -p test_rag_postgres_integration.py -v
```

执行时间 6.191 秒。错误用例 `test_two_connections_concurrent_begin_one_winner`：`PgVectorStore.begin()`（`locagent_service/rag_postgres.py:66`）在同时 INSERT 时抛出 `psycopg.errors.UniqueViolation`，约束名 `rag_vector_builds_build_key_dimensions_key`。当前 SQL 指定 `ON CONFLICT(build_key)`，表另有用于复合外键的 `UNIQUE(build_key,dimensions)`；本次实际观察到后者冲突未归一为预期的 `BuildConflict`。这是并发领取接口的待修缺陷，触发频率尚未测定；不将其归因于代理、TIME_WAIT 或数据库未 ready。未修改实现、放宽测试或通过反复重跑替代失败记录。

测试只终止其自己创建的一条数据库会话，未停止其他服务。新增 17 个随机 `public_preview_vi_*` schema 全部保留，旧 schema 集合保留。finally 已停止本次启动的容器，结束状态 exited，镜像、端口映射与卷身份不变；未删除数据。3140 个保护文件哈希全部不变，包括冻结实验及旧账本、原学习 README。

证据：`outputs/closeout-pgvector-20261017/tests.log`、`result.json`（含核验版本、17 个新增 schema、前后容器状态及保护结果）。本轮仅提交文档，未执行模型补验；7 元历史预留参数仍待核实。下一步应单独修复并发领取的唯一约束竞争，再补跑相关并发及全部 17 项集成测试，保持复合外键与维度约束。

### 2026-10-17 当前 engine 真实单题补验：通过

用户明确批准后，按同一固定仓库/commit/问题、新清单和新独立授权完成补验，详见 [完整验收](PUBLIC_SINGLE_SMOKE_20261017_ACCEPTANCE.md)。真实任务 `da3a7576-c848-4dc2-ae6c-21caca51e759` completed/success，3次HTTP200全部settled，精确deepseek-flash，13897输入/345输出tokens，高峰usage核算0.030554元，reserved=0。定位到TimestampSigner.unsign，手工核验过期判断正确。当前engine绑定一致，自有服务已停止，3205保护文件哈希不变。此前“当前版本缺真实验收”的待办已完成；pgvector并发错误及dense/hybrid接入等待办仍保留。这里的核算额不是已核对的控制台现金扣款。

### pgvector 并发修复及调用配额边界

已修复复合唯一索引竞争：事务内按schema/build键先加advisory lock，原约束不变。19项真实集成、60次重复并发/回滚、77项相关离线回归全部通过，历史失败保留。详见 [修复报告](PGVECTOR_CLAIM_FIX_20261017.md)。容器已停止，本阶段3199保护文件哈希不变。修复仅改变engine中的rag_postgres.py。暂停消息到达前真实补验已经用完3次调用，之后无新增请求；修复后版本未再真实验收，不重用旧授权或自动扩大调用额度。

### 最终只读复核

当前代码HEAD `79e021224de91a8e3f94d3162fd4b6ea32e9a457` 完整离线discovery：675通过、19数据库跳过、0失败/错误；19项真实数据库和60次重复并发证据另列，不重复相加。实际smoke对应eee52a4的138个engine文件已逐一与Git核对，执行窗口03:24:34.610931–03:24:44.800358 UTC；逐次HTTP客户端时间未记录。配置、轨迹和源码证明其使用BM25而非pgvector领取。详细证据与锁边界见 [最终只读复核](FINAL_READONLY_REVIEW_20261017.md)。本轮0新增模型请求，冻结物与旧账本不变。
