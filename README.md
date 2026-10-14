# LocAgent：可审计的异步代码定位服务

把自然语言问题定位到仓库中的文件和函数，并保存任务状态、检索轨迹和评估证据。**本分支基于开源 [LocAgent](https://github.com/gersteinlab/LocAgent) 改造**，重点是服务可靠性、任务专用执行约束与可复现评估；不是从零实现论文方法，也不自动修复代码。

默认演示使用内存中的两节点图和脚本 provider，不需要模型 key。原 prepared 路径仍由操作端固定 commit、构建图/BM25 索引并生成可信清单。新增可选的 [公开 GitHub Python 仓库预览](docs/PUBLIC_REPOSITORY_PREVIEW.md)：提交仓库链接和问题，后台固定 commit、准备可复用索引并返回可查询结果；本轮仅运行 fake provider，不评价定位质量、不调用付费模型。新增 [单题操作员授权层](docs/PUBLIC_REPOSITORY_AUTHORIZATION.md) 默认关闭，仅以 stub 验证预算预留、结算和未知结果不重放；尚未验收真实模型。HTTP 仍不接受任意本地路径或上传的 pickle。当前面向隔离的本地开发与复现，不是生产部署方案。验收记录见 [公开仓库闭环验收](docs/PUBLIC_REPOSITORY_ACCEPTANCE.md)，[中文交付复核](docs/PUBLIC_REPOSITORY_REVIEW.md) 明确说明固定空结果的 fake-only 含义和测试计数。

最新恢复验收与限流证据见 [2026-10-14 恢复报告](docs/PUBLIC_REPOSITORY_RESUME.md)。

[快速演示](#快速演示无需模型-key) · [开发与测试](#开发与离线测试) · [真实评估](#真实评估入口与配置边界) · [实测结果](#实测结果与解释边界) · [上游论文与引用](docs/UPSTREAM_README.md)

## 改造了什么

技术栈：Python、FastAPI/Pydantic、PostgreSQL/psycopg、独立 worker 进程、Docker Compose；定位沿用上游的代码图、NetworkX、图检索工具、BM25 与模型适配层。

~~~mermaid
flowchart LR
  U[客户端] -->|提交任务| A[FastAPI]
  A -->|持久化任务| D[(PostgreSQL)]
  D -->|领取任务| W[worker监督进程]
  W -->|每次attempt独立进程| G[GraphLocalizer]
  G --> R[图与BM25检索 / 模型调用]
  G -->|原子发布结果| W
  W -->|校验lease与fencing后写回| D
  U -->|查询状态、结果、attempts| A
~~~

- **可靠任务服务**：`Idempotency-Key` 支持同键同请求重放、不同请求返回409；`FOR UPDATE SKIP LOCKED` 支持多个 worker 领取任务。lease/heartbeat 与 owner、token、attempt、数据库时钟检查阻止过期执行者写回。
- **取消、超时与受限重试**：监督进程回收子进程；仅安全的 `demo-v1` 允许限次恢复/重试。真实来源执行中断转为 `needs_review`，不自动重放；取消不保证远端请求未计费。
- **代码检索增强**：结构图、实体读取和 BM25 提供代码证据；`suppress_repeats` 可折叠已经完整可见的重复返回，未读尾部不会冒充已读。这不是通用知识图谱问答或通用 GraphRAG 平台。
- **任务专用执行流程（harness）**：隔离旧引擎的全局图状态，约束轮次、工具页、输入大小和最终提交；`bounded-v1` 使用严格的 `finish(files, entities)`。候选指导只整理可见的可信图ID，不替代检索或放宽校验。
- **可复现评估**：固定仓库 commit、样本、模型参数、索引、运行时代码与标签口径；金标不进入模型输入或索引。配对比较、检查点、原始响应持久化和费用预留/结算用于审计；结果未知时保留完整预留并停止，不能声称模型调用 exactly-once。

实现与状态图见[架构说明](ARCHITECTURE.md)。

## 快速演示（无需模型 key）

前置条件：Linux 或 WSL2、已启动的 Docker Engine 与 Compose v2（支持 `--wait`）、Bash、curl、Python 3。在仓库根目录执行；首次构建需要下载镜像和依赖，但任务本身不访问模型服务。

~~~bash
docker compose up --build -d --wait
curl --noproxy '*' -fsS http://127.0.0.1:18080/health
~~~

健康响应包含 `status=ok`、`schema_version=2`。打开 [API 文档](http://127.0.0.1:18080/docs)，或在同一个 Bash 会话提交成功和失败演示：

~~~bash
api=http://127.0.0.1:18080
run_id="$(date +%s)-$$"

submit_demo() {
  curl --noproxy '*' -fsS -X POST "$api/tasks" \
    -H 'Content-Type: application/json' \
    -H "Idempotency-Key: readme-$1-$run_id" \
    -d "{\"problem_statement\":\"Locate render.\",\"demo_scenario\":\"$1\"}" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
}
ok_id="$(submit_demo success)"
error_id="$(submit_demo provider_error)"
printf 'success=%s\nprovider_error=%s\n' "$ok_id" "$error_id"

# 每项最多轮询60次（约60秒，另加HTTP耗时）；超时不重新提交。
# 子shell非零退出只结束本段轮询，不关闭当前交互shell。
(
for task_id in "$ok_id" "$error_id"; do
  terminal=false
  for attempt in $(seq 1 60); do
    task="$(curl --noproxy '*' -fsS "$api/tasks/$task_id")"
    state="$(printf '%s' "$task" |
      python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
    case "$state" in
      completed|failed|cancelled|needs_review)
        terminal=true
        printf 'task=%s terminal=%s\n' "$task_id" "$state"
        printf '%s\n' "$task" | python3 -m json.tool
        break ;;
    esac
    sleep 1
  done
  if [ "$terminal" != true ]; then
    printf '等待超时：task=%s，最后状态=%s；尚未完成，可继续GET查询。\n' \
      "$task_id" "$state" >&2
    exit 1
  fi
  curl --noproxy '*' -fsS "$api/tasks/$task_id/attempts"
  printf '\n'
done
)
~~~

| 场景 | 预期任务终态 | 预期结果 |
|---|---|---|
| `success` | `completed` | `result.status=success`，实体 `demo.py:render` |
| `provider_error` | `failed` | `error.code=model_error`，不泄露provider原始异常 |

重复相同幂等键和请求会返回原任务。查询入口为 `GET /tasks/{id}` 和 `GET /tasks/{id}/attempts`；取消为 `POST /tasks/{id}/cancel`；`POST /tasks/{id}/retry` 仅接受次数未耗尽的失败demo任务。任务 `completed` 不等于定位命中，仍须检查结果的 `success`、`empty` 或 `iteration_limit`。

**停止演示并保留数据库历史：**

~~~bash
docker compose down
~~~

不要添加 `--volumes` 或 `-v`。默认命名卷为 `locagent_pgdata`，再次启动会保留任务历史。API仅绑定本机 `127.0.0.1:18080`；PostgreSQL不发布主机端口，内部网络使用本地演示用的trust认证，不能直接用作公开部署。Compose将 `LOCAGENT_ALLOW_PAID` 固定为0，没有向容器挂载项目凭据文件。

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

已有证据分层：数据库/进程故障注入与Compose闭环在此前阶段验收；有界finish实现后全套离线 **403项**通过，相关独立复核 **57项**通过，随后真实序列化夹具校准又通过 **12项**。三组有重叠，不相加；最后一次只重跑了受影响模块。本次README整理没有重跑全套或容器验收。

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
- **未验证**：生产吞吐、公开部署安全、高可用SLA、模型权重不可变性及普遍质量/费用收益。数据库恢复证据与离线故障注入，不等于已验证真实模型的故障恢复。

建议按以下顺序阅读：

1. [架构](ARCHITECTURE.md) → [API](locagent_service/api.py)、[存储与状态机](locagent_service/store.py)、[worker隔离](locagent_service/worker.py)。
2. [定位适配层](util/localizer.py)、[有界协议](util/localization_protocol.py)、[检索工具](plugins/location_tools/repo_ops/repo_ops.py) → [离线测试](tests/README.md)。
3. [20题实测](NEW20_REAL_EVALUATION.md)、[10题实测](CANDIDATE_GUIDANCE10_EVALUATION.md) → [评估入口](locagent_service/phased.py)。

## 上游、论文与许可证

完整上游项目说明、CodeNib集成入口、论文原始复现步骤与BibTeX已保留在[上游README](docs/UPSTREAM_README.md)，包含原作者与研究贡献归属。论文结果不能作为本分支改造收益。

本项目遵循仓库中的 [Apache-2.0 LICENSE](LICENSE)；原许可证及上游引用保持不变。
