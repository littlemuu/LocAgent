# LocAgent：可审计的异步代码定位服务

把自然语言问题定位到仓库中的文件和函数，并保存任务状态、检索轨迹和评估证据。**本分支基于开源 [LocAgent](https://github.com/gersteinlab/LocAgent) 改造**，重点是服务可靠性、任务专用执行约束与可复现评估；不是从零实现论文方法，也不自动修复代码。

当前提供三条入口：无需模型 key 的离线 demo、公开 GitHub Python 仓库的 **fake preview**、操作员预先准备清单的真实评估链路。公开仓库入口已实现“链接＋问题 → 固定 commit → 静态代码图/BM25 → 后台任务 → 查询结果”；默认 fake 固定返回空定位，只验收流程。其真实 provider 授权与预算保护已通过 stub 测试，**新链接入口的真实模型端到端与定位质量尚未验收**。历史 SWE-bench 真实评估另有记录，见下文，不能与新入口混为一谈。

本项目面向隔离的本地开发与可复现评估；不自动修复代码，也不适合直接公网开放。

[快速体验](#快速体验) · [数据库升级](#已有数据库升级到-schema-v3) · [验收证据](#验收状态2026-10-14) · [真实评估](#真实评估入口与配置边界) · [后续路线](#后续路线尚未实现) · [上游论文与引用](docs/UPSTREAM_README.md)

## 改造了什么

技术栈：Python、FastAPI/Pydantic、PostgreSQL/psycopg、独立 worker 进程、Docker Compose；定位沿用上游的代码图、NetworkX、图检索工具、BM25 与模型适配层。

~~~mermaid
flowchart LR
  U[客户端] -->|提交任务| A[FastAPI]
  A -->|持久化任务| D[(PostgreSQL)]
  D -->|领取任务| W[worker监督进程]
  W -->|github-v1后台阶段| I[固定commit / 静态代码图与BM25 / 缓存]
  I --> G[GraphLocalizer工具循环]
  W -->|demo或prepared入口| G
  G --> R[fake或显式授权provider / 图与BM25工具]
  G -->|原子发布结果| W
  W -->|校验lease与fencing后写回| D
  U -->|查询状态、结果、attempts| A
~~~

- **可靠任务服务**：`Idempotency-Key` 支持同键同请求重放、不同请求返回409；`FOR UPDATE SKIP LOCKED` 支持多个 worker 领取任务。lease/heartbeat 与 owner、token、attempt、数据库时钟检查阻止过期执行者写回。
- **取消、超时与受限重试**：监督进程回收子进程；`demo-v1` 和未带授权的 `github-v1` fake 任务允许限次恢复/重试。prepared/授权任务的结果不明中断转为 `needs_review`，不自动重放；取消不保证远端请求未计费。
- **公开仓库静态准备**：只接收规范化 GitHub HTTPS 公开 Python 仓库，ref 固定为 commit；后台下载、静态解析和建索引，不执行仓库代码。按 repo/commit/config/engine 哈希复用索引，用锁与原子发布避免重复构建和读取半成品；每次问题单独持久化，阶段与失败诊断可查询。
- **代码检索增强**：结构图、实体读取和 BM25 提供代码证据；`suppress_repeats` 可折叠已经完整可见的重复返回，未读尾部不会冒充已读。这不是通用知识图谱问答或通用 GraphRAG 平台。
- **任务专用执行流程（harness）**：隔离旧引擎的全局图状态，约束轮次、工具页、输入大小和最终提交；`bounded-v1` 使用严格的 `finish(files, entities)`。候选指导只整理可见的可信图ID，不替代检索或放宽校验。
- **可复现评估**：固定仓库 commit、样本、模型参数、索引、运行时代码与标签口径；金标不进入模型输入或索引。配对比较、检查点、原始响应持久化和费用预留/结算用于审计；结果未知时保留完整预留并停止，不能声称模型调用 exactly-once。

实现与状态图见[架构说明](ARCHITECTURE.md)。

## 快速体验

以下命令从仓库根目录运行，前置条件为 Linux/WSL、Docker Engine、Bash、curl 和已安装依赖的 Python 环境。首次准备环境或镜像需要网络；“离线 demo”指任务不调用模型或下载目标仓库。新 Python 环境的安装命令见下一节。

### 1. 本机离线 demo：API → 数据库 → worker → 结果

沿用 `locagent_service.demo` 管理的环境（API `8000`、PostgreSQL `55432`）。**已有 v2 数据库先看下一节的升级步骤**；`up` 也会调用数据库初始化，因此不是只启动进程。

~~~bash
PYTHON="${PYTHON:-$PWD/.venv/bin/python}"
export LOCAGENT_ALLOW_PAID=0 LOCAGENT_PUBLIC_LIVE=0
"$PYTHON" -B -m locagent_service.demo up
curl --noproxy '*' -fsS http://127.0.0.1:8000/health
"$PYTHON" -B -m locagent_service.demo run --scenario success
"$PYTHON" -B -m locagent_service.demo run --scenario provider_error
"$PYTHON" -B -m locagent_service.demo down
~~~

成功演示返回 `completed`、实体 `demo.py:render`；错误演示返回 `failed`、`model_error`。`down` 保留 PostgreSQL volume 与任务历史。状态可用 `demo status` 查看，交互 API 文档在 `http://127.0.0.1:8000/docs`。

也可使用独立的 Compose demo（Compose v2，API `18080`），不要与上述管理器混用端口、配置和数据卷：

~~~bash
docker compose up --build -d --wait
curl --noproxy '*' -fsS http://127.0.0.1:18080/health
curl --noproxy '*' -fsS http://127.0.0.1:18080/tasks \
  -H 'Content-Type: application/json' \
  -d '{"problem_statement":"Locate render.","demo_scenario":"success"}'
# 使用响应 id 查询 GET /tasks/{id}；停止时保留 volume：
docker compose down
~~~

Compose 按 PostgreSQL 就绪 → `migrate` 成功 → API/worker 顺序启动，健康响应应为 `schema_version=3`。默认 volume 为 `locagent_pgdata`，不要使用 `down -v` 或 `--volumes`。数据库不发布主机端口；内部 trust 认证只用于本地隔离演示，不能用于公网部署。

### 2. 公开 Python 仓库 fake preview

先按[预览启动说明](docs/PUBLIC_REPOSITORY_PREVIEW.md#isolated-local-launch)配置**独立**数据库、`public_preview_` schema、缓存目录，以及 API `18089` 和 worker；该说明包含完整环境变量与显式初始化命令。不要把预览测试指向现有 demo 数据库。默认 Compose 配置不会开启此入口。

启动后提交公开仓库和问题（此步骤会访问 GitHub 下载源码，但不调用模型）：

~~~bash
curl --noproxy '*' -fsS http://127.0.0.1:18089/tasks \
  -H 'Content-Type: application/json' \
  -d '{"source_id":"github-v1","repository_url":"https://github.com/pallets/itsdangerous","ref":"2.2.0","problem_statement":"Find how URL safe timed serialization signs data.","timeout_seconds":300,"max_attempts":3}'
~~~

API 返回 HTTP 202、任务 ID 和 `Location`；对该地址执行 GET 可查 `status`、`progress.stage`、固定 commit、cache hit、诊断与最终结果。`ref` 可省略，省略时解析默认分支并固定 SHA。fake 会调用真实图/BM25 工具，最后固定 `finish(files=[], entities=[])`；**`completed` 不等于定位命中**。匿名 GitHub 限额可能使下载失败，不要把历史成功当作随时可用的保证。

所有入口共用 `GET /tasks/{id}`、`GET /tasks/{id}/attempts`、`POST /tasks/{id}/cancel`；`POST /tasks/{id}/retry` 只接受仍有次数的安全失败任务。`Idempotency-Key` 可防止重复提交；授权任务禁止自动重放。真实 provider 需另走[单题授权与预算流程](docs/PUBLIC_REPOSITORY_AUTHORIZATION.md)，不是在请求里任填模型/key 即可启用。

## 已有数据库升级到 schema v3

代码现在要求 **v3**：在 v2 的 `tasks` 上增加 `progress jsonb` 并更新版本；保留原任务和 attempts，不重置预算或授权。API/worker 只检查 schema，不自行迁移。2026-10-14 最后记录的旧本机 demo 已停止、数据库仍为 v2；本次 README 更新没有连接数据库或执行迁移，实际状态以本地检查为准。

对 `demo` 管理器创建的旧数据库：先确认已停止旧 API/worker、保留原 `outputs/stage2/demo/runtime.json` 与 `locagent-stage2-pg-data` volume，并备份需要保留的数据。不要删除 runtime 文件来“重新初始化”，也不要重新生成旧库凭据。确认后运行：

~~~bash
PYTHON="${PYTHON:-$PWD/.venv/bin/python}"
export LOCAGENT_ALLOW_PAID=0 LOCAGENT_PUBLIC_LIVE=0
# 仅在旧 demo 仍运行时，先执行："$PYTHON" -m locagent_service.demo down
"$PYTHON" -B -m locagent_service.demo db
"$PYTHON" -B -m locagent_service.demo up
curl --noproxy '*' -fsS http://127.0.0.1:8000/health
~~~

`demo db` 读取原本地 runtime 配置、启动既有容器并调用 `TaskStore.initialize()`；重复初始化 v3 不会重建表。**当前该命令的成功提示仍硬编码为 “schema version 2”**，属于显示文字过时；以随后 `/health` 的 `schema_version=3` 为准。若失败，保留原数据检查日志，勿删卷、删 runtime 或清空 schema。本轮只记录该显示问题，没有修改实现。

自管数据库使用已在本地安全设置的 `LOCAGENT_DATABASE_URL` / `LOCAGENT_SCHEMA`，停止对应旧进程并备份后，显式运行 `"$PYTHON" -m locagent_service.db`。不要打印 DSN 或提交凭据。Compose 使用自身独立卷和 `migrate` 服务，不能替代上述旧 demo 的升级。所有实际配置、授权、账本与响应产物留在忽略目录，`.env.example` 只是示例；`.gitignore` 不是秘密隔离机制。

## 验收状态（2026-10-14）

| 范围 | 已有证据 | 不代表什么 |
| --- | --- | --- |
| 自动测试 | 433 项离线 + 46 项隔离 PostgreSQL，共 **479 项**；额外 16 项授权复测是子集，不累加 | 不代表实模质量或公网安全 |
| 新公开仓库入口 | itsdangerous `2.2.0` 固定 commit 的真实静态下载/建图，cache miss、hit 两个 fake 任务完成 | fake 固定空结果，不是实模语义定位验收 |
| 新授权 provider | stub 验证精确授权、满额预留、原始响应结算、并发与未知结果不重放 | 未完成供应商连通性、真实计费及单题实模 E2E |
| 历史 SWE 评估 | prepared/phased 路径已有真实模型对照实验，结果见下表 | 不能作为新链接入口的验收或普遍收益证明 |

命令、失败/限流诊断和计数口径见[完整验收](docs/PUBLIC_REPOSITORY_RESUME.md)、[历史验收](docs/PUBLIC_REPOSITORY_ACCEPTANCE.md)与[能力边界复核](docs/PUBLIC_REPOSITORY_REVIEW.md)。本次 README 更新只做静态核对，没有重跑全套测试或启动数据库。

## 开发与离线测试

无需模型key或数据库即可运行单元/HTTP/合成评估测试。已有兼容环境可直接使用；新环境可按本地已验收的Python 3.12准备（Compose镜像使用Python 3.10）：

~~~bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt -r requirements-service.txt
~~~

在无真实凭据的开发副本中运行：

~~~bash
LOCAGENT_ALLOW_PAID=0 sh scripts/check_local.sh

# 仅预算耗尽收尾回归：
LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True \
  HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p 'test_budget_finish.py' -v
~~~

`check_local.sh` 调用 `unittest discover` 并检查diff；可通过 `PYTHON` 指定解释器。测试使用合成provider、MockTransport及临时账本，不是模型质量评测。`.gitignore` 只防止提交，**不能阻止SDK或进程读取 `.env`**，不要把“被忽略”当作凭据隔离。

更重的 `sh scripts/check_local.sh --postgres` 需要已配置的本地测试数据库；`--compose` 会构建镜像并新建独立验收volume，结束保留volume。它们不是默认离线测试的一部分。具体前置条件及测试分类见[测试说明](tests/README.md)。

## 真实评估入口与配置边界

操作入口是 `locagent_service.prepare`（固定Git来源与图/BM25清单）、`locagent_service.evaluate`（配对评估）及 `locagent_service.phased`（分阶段、共享限额及检查点）。可安全查看帮助：

~~~bash
.venv/bin/python -m locagent_service.prepare --help
.venv/bin/python -m locagent_service.evaluate --help
.venv/bin/python -m locagent_service.phased --help
.venv/bin/python -m locagent_service.configure --help
~~~

真实模型配置只示意变量名，默认保持付费关闭：

~~~dotenv
DEEPSEEK_API_KEY=<由操作者在本地安全配置，不提交>
LOCAGENT_ALLOW_PAID=0
~~~

支持显式 `--env-file` 的CLI要求普通本地文件、权限0600，仅允许上述两个变量；检查器只报告是否存在，不显示值。分阶段入口另走审批与环境准入，不能把其他CLI的参数照搬过来。不要读取、复制或提交现有凭据以“复现”他人的实验。

操作型cohort配置默认不随Git分发；[示例](locagent_service/phased_cohorts.example.json)是空样本、零预算的结构，不能直接执行。新的真实评估必须重新核对来源/代码/依赖绑定、样本与标签、精确计划、有效价格与完整费用预留，经独立复核和明确预算授权后才能显式开启。CLI生成的proposal只是草稿，旧授权不可复用；mock模拟不能升级为live。出现未知付费结果须停止核查，不能自动重试。本README不提供默认付费运行命令。

## 实测结果与解释边界

| 实验（关 → 开） | 有效finish | 文件Recall@3 | 函数Recall@3 |
|---|---:|---:|---:|
| 固定20题，比较重复抑制 | 19/20 → 18/20 | 90% → 80% | 68.52% → 62.04%（18题适用） |
| 新10题中的主评8题，比较候选指导 | 87.5% → 87.5% | 87.5% → 87.5% | 75% → 68.75%（8题） |

20题比较完成40臂、120次请求。新10题按2题门槛与8题主评分开统计，固定 `suppress_repeats=False`，累计59次请求，费用**保守上界0.841358元，不是账单**。主评总token下降1.66%，但xarray指导开启臂因工具预算早退少调用一次，**不能包装成效率提升**。

两轮都是小样本单次比较，不能称严格盲测，也未证明优化成功。候选指导默认关闭；详见[20题报告](NEW20_REAL_EVALUATION.md)和[10题候选指导报告](CANDIDATE_GUIDANCE10_EVALUATION.md)，两者不合并计算效果。

评分按预先固定的适用任务宏平均Recall@3，不是“所有函数中命中几个”的总体比例。非法、失败或缺失答案按固定规则计零。20题函数口径为18题、27个目标，另外2题NA不冒充零分；无法用图实体表示的构造函数真值仍保留，不用类ID代替函数计分。

## 已知限制与阅读路径

- **图实体边界**：严格finish中，文件只能放在 `files`；`entities`只接受存在的函数/类ID并归属所提交文件。变量/赋值别名不能作为实体；没有独立 `__init__` 节点时提交所属类，但这不自动获得构造函数的函数召回分。一个非法项会拒绝整份提交。
- **默认值有区别**：核心 `LocalizationOptions.suppress_repeats=False`，HTTP `TaskOptions` 默认True；比较时显式指定。`candidate_guidance=False`，仅支持 `bounded-v1`，未加入HTTP TaskOptions；核心搜索协议默认仍是legacy。
- **有界finish修复有代价**：24 KiB总工具交付预算内始终预留4 KiB结束控制；候选开时另预留4 KiB指导。工具页关/开额度为 **20,480/16,384字节，含包装、元数据和转义**，两者均比修复前少4,096字节，可用正文更少，会更早截断。耗尽后在原额度内尝试一次仅finish收尾，严格校验不变；该修复未进行新的付费质量验证。
- **部署边界**：尚无完整 OS 沙箱、公网鉴权和总缓存配额；Python 子进程/RLIMIT 不是完整隔离，不应直接公网开放。
- **未验证**：生产吞吐、公开部署安全、高可用SLA、模型权重不可变性及普遍质量/费用收益。数据库恢复证据与离线故障注入，不等于已验证真实模型的故障恢复。

建议按以下顺序阅读：

1. [架构](ARCHITECTURE.md) → [API](locagent_service/api.py)、[存储与状态机](locagent_service/store.py)、[worker隔离](locagent_service/worker.py)。
2. [定位适配层](util/localizer.py)、[有界协议](util/localization_protocol.py)、[检索工具](plugins/location_tools/repo_ops/repo_ops.py) → [离线测试](tests/README.md)。
3. [20题实测](NEW20_REAL_EVALUATION.md)、[10题实测](CANDIDATE_GUIDANCE10_EVALUATION.md) → [评估入口](locagent_service/phased.py)。

## 后续路线（尚未实现）

1. **单题真实模型端到端**：先明确题目、数据接收方、模型和预算授权，再验证新公开仓库入口的请求、原始 usage、结算与可用定位结果；未知结果停止核查，不重放。
2. **混合检索**：研究按代码结构切块并生成 embedding，用 PostgreSQL + pgvector 保存向量，与现有 BM25 通过 RRF 融合，再结合代码图扩展证据。向量检索尚未实现，embedding 模型尚未选定。
3. **索引版本与增量准备**：按 repo、commit、embedding model、chunker 版本隔离；复用未变块，完整验证后原子发布索引，避免跨版本混用或读取半成品。
4. **固定评估协议**：分开开发集与留出验证集，对比 BM25 基线、混合检索和图扩展的 Recall、成本与延迟；保留失败、无提升及退化结果，不用开发集调参成绩代替验证结果。

## 上游、论文与许可证

完整上游项目说明、CodeNib集成入口、论文原始复现步骤与BibTeX已保留在[上游README](docs/UPSTREAM_README.md)，包含原作者与研究贡献归属。论文结果不能作为本分支改造收益。

本项目遵循仓库中的 [Apache-2.0 LICENSE](LICENSE)；原许可证及上游引用保持不变。
