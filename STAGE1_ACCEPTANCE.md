# 第一阶段：可独立调用的单次定位核心

第一阶段只包含请求、结果、错误契约和单次定位适配。没有 API、数据库、
任务队列或部署；不自动下载仓库、数据集或索引。

## 复现

在 Ubuntu / WSL 的仓库根目录，使用现有 CPU 虚拟环境：

```sh
LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 \
  .venv/bin/python -B -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
```

该命令包含原有 14 个测试和一阶段 34 个测试，共 48 个 unittest 方法。
fixture 是内存中的两节点图。
关键词检索测试另外在临时目录生成小型 BM25 索引，并在退出时删除。
fake provider 返回确定的响应，实际执行共享主循环、解析器、图工具和结果解析。
测试在依赖导入前阻断 TCP、UDP、DNS；即使依赖吞掉连接异常也会判定失败。
LiteLLM 使用自带价格元数据，不请求远端价格表。不需要凭证或新增依赖。

已有 `outputs/day1` 历史 fixture 时，还可运行旧 Day4–6 smoke：

```sh
.venv/bin/python -B tests/run_historical_smokes.py
```

此 runner 阻断网络和真实模型，允许 multiprocessing 使用本机 AF_UNIX IPC。
Day5 会按照原脚本行为新建一个 `outputs/day5/trace-*` 目录，不覆盖旧产物。
历史 fixture 缺失时会明确报错；一阶段 unittest 不依赖这些文件。

## 最小调用

```python
from util.localization_contract import LocalizationRequest, LocalizationOptions
from util.localizer import GraphLocalizer

request = LocalizationRequest(
    instance_id="demo__demo-1", repo="demo/demo", base_commit="a" * 40,
    problem_statement="Locate the render function.",
)
localizer = GraphLocalizer.from_graph(
    prepared_graph,                       # 调用方准备好的、可信的图
    provider=scripted_provider,            # 显式注入 callable，不存在默认模型调用
    model_name="offline-test",
    options=LocalizationOptions(max_iterations=6, suppress_repeats=True),
)
result = localizer.localize(request)
print(result.to_dict())
```

`tests/test_stage1_localizer.py` 给出了完整小型图和 scripted provider。
provider 接收原来 `request_model(**kwargs)` 的参数，并返回 LiteLLM ModelResponse
兼容对象。新入口不会导入 `auto_search_main` 或改动代理环境。

新入口的 `finish` 工具参数严格为 `{"thought": "最终定位文本"}`；空字符串表示
正常空结果。缺少 thought、非字符串或额外字段在 provider 边界判为
`invalid_response`，不会进入引擎后变成执行错误。发给 provider 的 schema 与此
约束一致，采用独立副本，不改动旧 CLI 的 FinishTool。文本 `<finish>` 路径仍保留。
最终定位支持图中已知的根文件（如 `demo.py`）以及原有嵌套文件；根文件匹配
不从绝对路径、反斜杠或 `../` 中截取文件名。旧 CLI 的嵌套路径提取行为保持。

真实引擎可以通过 `GraphLocalizer.from_index_dir(index_dir, ...)` 读取本机已准备的
`<instance_id>.pkl`。精确实体、短名称、按行和图结构工具使用该图。
关键词检索还需要注入已准备的 `module_retriever`，并配置 `bm25_index_dir`；
缺少其中的资源就抛出 `index_unavailable`，不会尝试构建或下载。
`module_retriever` 必须对应同一图，调用方应在进入定位前准备它。

`LiteLLMProvider` 是显式的真实模型适配器，构造时不请求模型；调用时有 60 秒
请求超时且不自动重试。用户授权真实模型运行后才能使用；本次验收未调用它。
已有 `request_model` 等 callable 也可以注入。模型配置和凭证不在请求契约中。

## 契约

保留用户编写的四个请求字段和非空检查，原始字符串不被 strip 修改。
进入引擎时使用独立规范化 task。四字段必须为字符串；`instance_id` 必须是安全
文件名组件，拒绝路径分隔符、绝对路径、控制字符及保留文件名；`repo` 为
`owner/name`，`base_commit` 为完整 40 位十六进制 SHA。被修改过的请求会再次校验。
这些检查只验证格式，不证明仓库存在或索引确实对应指定提交。

结果是一份单次结果，定位列表不再套多次采样的外层列表：

| status | 含义 |
| --- | --- |
| `success` | 正常结束，并有经过当前图验证的文件定位；实体列表可以为空 |
| `empty` | 使用 finish 正常结束，且最终定位内容为空 |
| `iteration_limit` | 没有 finish 即到达迭代上限；最终定位列表为空，但保留账本和消息 |

结果同时包含 `iterations`、非负 token 用量、原始最终输出、`return_records`
和消息。缩短工具消息不会删掉账本原文；每次尝试创建独立账本。
非空但无法解析到合法文件的最终回答属于 `invalid_response`，不会冒充正常空结果。

错误抛出 `LocalizationError`，可调用 `to_dict()` 获取稳定 `code` 和简短消息：
`invalid_request`、`index_unavailable`、`model_error`、`timeout`、`invalid_response`、
`execution_error`、`busy`、`output_error`。输入错误同时仍是 `ValueError`，兼容原测试。
provider 的原始异常正文不会出现在公开错误中。

## 状态与安全边界

`run_search` 是从原主循环抽出的实际共享实现。CLI 的 `auto_search_process`
仍接受原参数、把 tuple 或 BadRequest 字典写入原 queue；外层多进程、采样和
文件命名未改动。工具返回值的解释从 eval 改为 literal_eval。

新图适配器在运行时独占旧工具全局状态，重叠适配器调用明确抛出 `busy`。
结束、异常或 KeyboardInterrupt 都恢复原图、搜索器、索引配置和准备函数，
并释放锁；不会创建或删除 playground。图被复制，调用方图不被修改。
工具执行只接受 AST 检查过的 `print(allowed_tool(...))` 和字面量参数，拒绝
任意 Python、额外语句及内部 `_return_records` 等参数。

定位本身不写输出文件。调用方可显式 `write_result(result, trusted_output_root)`，
只创建 `<instance_id>.json`，不覆盖既有文件。WSL 的 dir_fd、O_EXCL 和 O_NOFOLLOW
固定输出目录并拒绝目录本身及目标文件符号链接；根目录配置必须来自可信调用方。

## 已验证与限制

2026-10-06，独立复验发现根文件和 finish 参数边界遗漏，修复并增加 5 个回归方法。
在现有 Ubuntu WSL 虚拟环境中完整运行：48 项 unittest 全部通过
（7.270 秒），Day4–6 三份历史 smoke 全部通过。网络和真实模型调用检查均通过。
Day6 仍复现第二次工具消息 2493 → 259 字符；账本原文保持完整。
`git diff --check` 通过，8 个 Python 文件的 compile 检查及新增文件空白检查通过。
HEAD 保持 `08385512ef5ae9b02f4b32a1e10d6c86ee02a2c3`，没有暂存、提交或推送。
用户原有 `tests/test_localization_contract.py` 未修改。

离线测试覆盖请求及路径安全、真实主循环工具链、抑制开关、JSON 序列化、
成功/空结果/迭代上限、provider 和 SDK 超时、错误脱敏、缺索引、准备好的 BM25、
未知工具、任意代码拒绝、输入修改后重校验、重复运行隔离、异常与取消恢复、
明确 busy、历史 CLI queue 协议，以及输出不覆盖和符号链接拒绝。
新增回归覆盖根文件的真实工具和解析链、非法根路径、旧 CLI 嵌套路径兼容、
finish 缺字段/未知字段/非字符串/非对象参数，以及合法 finish 和 schema 副本隔离。

尚未验证真实模型质量或费用、真实远端请求、完整 Loc-Bench。
ruff、mypy、pyright、black 等工具不在现有 WSL 环境中；不为本任务安装它们。
使用 Python compile/AST 检查和 Git 空白检查作为基础静态验证。
依赖仍有原有 Pydantic/LiteLLM 弃用警告。

本适配器不是可并发的服务或 OS 沙箱。旧 CLI/直接工具调用不使用适配器锁，
不能与适配器共享同一进程同时运行；后续 worker 应采用进程隔离。
provider 超时被分类，但本阶段没有整个任务的硬截止或强制终止机制。
可信 graph loader 和检索器属于调用方依赖，不限制其任意代码。
pickle 仅适合操作者生成的可信本机索引，禁止直接接收用户上传的 pickle。
图没有内置提交证明，操作者仍需确保 graph、BM25 与 repo/base_commit 相符。
