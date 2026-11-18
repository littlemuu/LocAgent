# 候选列表 → 正文 → 调用线索：离线改进

2026-11-10。本轮只实现默认关闭的核心选项和离线验证；没有真实模型请求、没有读凭据、没有重用或修改历史账本，也没有启动、停止或重启用户服务。

## 改动

通过 `LocalizationOptions(search_protocol="bounded-v1", candidate_drilldown=True)` 显式启用。默认 False，既有 autonomous_reread=True、candidate_drilldown=False 仍走原 v2 逻辑。CLI、Web、服务和历史付费实验不自动启用新选项；未来实验须重新准备并批准绑定当前源码的新计划。

- 可信工具渲染器产生、且完整送达上下文的 function 候选提示，可进入 `reread_visible_entity` 的可读集合。不是从仓库文本匹配或推测 ID；候选必须是图中实际函数。
- 同样支持既有已送达压缩类签名（需原 autonomous_reread=True 开启签名捕获）。同轮工具批次新出现的候选不授权该批次猜测补读。
- 模型自行选择补读，读取原 get_entity_contents 正文；正文里的调用名称只是源码线索，继续用原搜索/读取工具调查。实现没有自动遍历调用图、没有自动选择“正确”候选、没有答案特例或标注读取。
- 重复引用、未送达尾部、有间隙的片段、类/文件提示、普通文本伪造提示均不扩大可读集合。仍共享最多两次补读尝试、原轮数和字节预算。控制提示预留 2048 字节，在原总预算内，不增总额度。新增提示因此可能挤占正文空间，不能称为零成本优化。
- 函数提示并不意味着正文尚未读过；本版允许对已读函数再发起一次读取；若 suppress_repeats=True，原工具可能仅返回重复通知。新诊断用 returned_content=repeat_notice、status=repeat_notice_delivered 区分，不把通知当正文。它不保证模型会使用该入口。

## 7220 的两种证据，不能混写

1. **原始录制送达重放**：夹具复制原 on-result 的 output-3 文本、可信候选 spans 和最后一条送达区间，附原文件、源码归档及源码哈希。Node.repr_failure 的提示区间 1846–1969 完整落入送达 0–1970；后面的 Collector.repr_failure 未完整送达，不会获准。原 v2 签名集合为空，新候选集合能包含 Node.repr_failure。原第三次请求工具只有 finish，历史 attempts 仍为空。此测试重放的是送达证据，不是全量重跑原模型轨迹。
2. **独立脚本反事实**：小图中使用公开固定源码的 Node.repr_failure 和 Node._repr_failure_py，另加合成同名候选形成折叠列表。四轮脚本依次检索列表、选择正文、根据正文调用读取被调用方法、提交；可以送达包含 os.getcwd() 的正文。选择由测试作者脚本写死，不是模型自行选中，更不是把原三轮实验提高到四轮后的质量结果。

因此：本轮证明入口与正文路径可达，并修补“候选提示不是签名，所以补读集合为空”的覆盖缺口。**没有证明真实定位质量提高，也不能挽救原 7220 三轮轨迹已经没有下一次工具机会的事实。** `get_entity_contents` 原本就能按精确 ID 读取正文；改进是显式候选入口和提示，不是新增源码权限。

## 实现与测试文件

- `util/candidate_drilldown.py`：候选证据适配和独立提示。
- `util/localization_contract.py`、`util/localizer.py`、`util/localization_protocol.py`：严格默认关闭选项及原循环接入。
- `tests/test_candidate_drilldown.py`：9 个新增测试，严格选项、默认一致、合成调用路径、同批次拒绝、完整/间隙/类型/重复边界、两次限额、7220 录制证据和脚本反事实。
- `tests/fixtures/candidate_drilldown_7220.json`：仅最小公开源码及已有送达录制，不含凭据、付费授权或标注。

## 验证状态

新增 9 项全部通过。最终聚焦回归 93 项全部通过（包含新增 9 项，不可相加），覆盖自主补读、可见签名、候选提示、bounded 协议、预算收束和行为源码绑定。日志：`verification/candidate-drilldown-20261110/focused-tests.log`。

复审修正前全量离线 discovery 已执行：Ran 791 tests，FAILED（failures=1, errors=13, skipped=19），耗时 127.329 秒。不能称为全套通过。日志为同目录 `full-tests.log`。11 个 error 项来自缺失历史冻结文件（含 1 个 setUpClass：3 项 bailian retrieval、7 项 expanded gate、1 项 expanded resume），2 个 error 来自旧 StageOne 队列测试依赖的 torch 未安装。1 个 failure 是父进程死亡测试：Mac 没有 Linux prctl 符号，子进程在设置 PDEATHSIG 时失败，随后等待 pidfile 断言失败。没有为消除失败安装依赖、伪造历史工件或修改这些旧测试。未跑真实 PostgreSQL、Compose 或真实模型质量实验；不需要启动这些服务来验证本次核心选项。项目目录没有 .git，因此不能声称完成 git diff --check 或提交。

复现聚焦测试（从项目根目录运行）：

```sh
TMPDIR=/private/tmp LOCAGENT_ALLOW_PAID=0 LITELLM_LOCAL_MODEL_COST_MAP=True HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 PYTHONPATH="$PWD:$PWD/scripts:$PWD/tests" .venv/bin/python -B -m unittest test_candidate_drilldown test_autonomous_reread test_visible_signatures test_candidate_guidance test_bounded_protocol test_budget_finish test_engine_binding -v
```

### 排错记录

首轮两个脚本测试失败，断言显示首次检索已返回正文，而不是折叠候选列表。原因是测试夹具同名候选数量不足以触发原检索器的 >3 折叠阈值，且根目录 other.py/extra.py 不匹配原 `**/*.py` 默认范围。修正为 src/ 下至少四个同名候选后，8/8 通过。生产检索阈值及默认文件范围未为测试修改。

5 个变更 Python 文件通过 AST 语法检查；两个新 Python 文件无行尾空白。没有 .git，不把该检查冒充 git diff --check。

### 独立复审修正

复审指出已读函数可能返回重复通知，初版 delivered 无法区分正文与通知。现以可信 repeated span 标记 returned_content 并使用 repeat_notice_delivered，新增 suppression=True 回归。另新增 candidate_drilldown.combined_delivery_bytes，作为 24576 字节预算核算指标：累计工具消息及反馈，加两类提示各自的最大一次字节数，并仅在预算 closing 时计入 finish 收束提示。它不是跨轮累计请求流量、token 或费用；自然最后轮 finish 提示不计入该字段。原 candidate_guidance 的同名旧诊断不用于新模式总开销比较。93 项最终聚焦回归全过；最终全量运行日志另存 full-tests-final.log：Ran 792 tests，129.773 秒，仍为 failures=1、errors=13、skipped=19，与上轮同类环境/工件问题；保留先前失败日志，不称全套通过。

结束时复核夹具来源 pytest-7220-on-result.json 的 SHA-256 与创建夹具时一致。未改写原实验结果。

独立只读复审已确认重复通知分类和提示预算核算两项修正解决原问题，未发现新的阻断；复审没有独立运行测试，运行结果来自上述本轮日志。
