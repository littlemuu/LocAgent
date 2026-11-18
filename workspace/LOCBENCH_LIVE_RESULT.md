# LocBench 两题真实试跑：异常停止，未重试

2026-11-13。用户明确批准发送两题题面、提示、工具定义、相关源码证据及本题本组历史，最多16请求/34元后，核对固定方案和无重复启动，登记一次性授权并执行了一次。**最终12请求，2组完成、1组失败、1组未运行；费用保守上界 ¥0.106498，无未知请求费用。未重试、未补跑、未修改执行代码。**

冻结方案 hash：`6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9`。
机器验收：[LOCBENCH_LIVE_ACCEPTANCE.json](verification/LOCBENCH_LIVE_ACCEPTANCE.json)。

## 运行范围与前置核对

- 同一 OpenHands SDK1.62.0、DeepSeek `deepseek-flash`，非思考、temperature0、每组最多4请求/2048输出tokens。两题固定源码/题面/评分/工具策略与已冻结计划一致。
- 当前登录的 DeepSeek 账户显示 CNY，其“产品定价”打开[官方中文价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)；版本仍为 DeepSeek-V4.1-Flash-1017，高峰未命中输入2、输出8元/百万tokens，符合预算假设。复用既有私有 `.env`，无本地覆盖，未进入API keys页面或输出密钥。可见账户与key未作额外密码学绑定，沿用此前同一账户配置范围。
- 启动前生产授权目录不存在；13份旧生产子账均无未决请求且摘要未变。旧1024输出token批次的预留额与当前2048配置不同，按各自冻结规则和原receipt核验，未修改旧账本或复用旧批准。
- 进程正常领取本次授权，真实命令只启动一次。退出码1，停机原因 `finish_message_contract_error`；SQLGlot基础组未启动。授权已领取，不能重复使用。

## 实际结果

| 题目/组 | 状态 | 请求 | 调查工具调用 | LocAgent调用 | 耗时 | 费用上界 |
|---|---|---:|---:|---:|---:|---:|
| Loguru 基础 | 正常终答 | 4 | 7 | 未提供 | 11.44s | ¥0.034822 |
| Loguru 检索可用 | 正常终答 | 4 | 7 | **0** | 10.07s | ¥0.035708 |
| SQLGlot 检索可用 | 终答契约失败 | 4 | 6 | **0** | 10.90s | ¥0.035968 |
| SQLGlot 基础 | not_run | 0 | 0 | 未运行 | — | ¥0 |

已执行的调查工具只有 list_files、search_text、read_file。检索组前三轮开放 LocAgent，wire `tool_choice=auto`；模型没有选择它。末轮仅提供 finish。没有强制检索或因未选择而补跑。

**唯一完整配对为 Loguru**：两组都返回5个文件，参考文件 `loguru/_better_exceptions.py` 均在第5位：文件 precision0.2、recall1、F1约0.3333、MRR0.2。两组各返回3个实体，但均未包含参考修改函数 `ExceptionFormatter._format_list`，实体 recall/F1均为0。回答主要解释如何增加现有异常格式化测试，并明确没有读到格式化函数的正文。

这只反映与冻结“参考补丁修改位置”标签的匹配，不是回答内容盲评。题面以增加RecursionError测试为主，参考修改却位于格式化实现；因此不能把实体未命中简单等同为回答完全无用，亦不能将文件列表中出现目标文件当成充分理解。

SQLGlot失败组的原始终答列出了 `Parser._parse_set_item_assignment`，但**未通过finish协议，不计作有效成功定位**。原始回答也承认没有读到函数正文，部分因果解释属于推断。基础组未运行，不能做该题配对胜负比较。所有模拟和真实历史记录保留，不把未运行的组当作模型尝试后失败。

## 已确认的停止原因

SQLGlot第4次回包 HTTP200、完整JSON、`finish_reason=tool_calls`，输出563 tokens，远低于2048上限；finish的message含：

```json
{
  "files": ["..."],
  "entities": ["..."],
  "answer": "...",
  "entities_note": null
}
```

本次实际发送的schema对message声明 `additionalProperties: false`，仅允许 files/entities/answer。额外 `entities_note` 触发 `structured_finish()` 的字段集合校验。外层summary是SDK声明的可选字段，不是此次拒绝原因。没有字符长度硬限制、没有token截断，也没有证据表明是HTTP故障。

离线诊断在副本上只投影三个既定字段后可通过这一结构校验，证明额外字段是当前直接触发点；**未改写原回包、未追认原终答、未更改分数或放宽运行规则**。完整原始回包与当时schema见 [LOCBENCH_FINISH_EXTRA_FIELD_INCIDENT.json](verification/LOCBENCH_FINISH_EXTRA_FIELD_INCIDENT.json)。

另一个可观察的接入问题：SQLGlot两次read_file使用offset5960/5969，却得到约145行起的源码片段。该工具offset是渲染文本字符游标；这些值接近目标函数行号，且原终答说“read returned an unrelated offset”。这支持“模型可能将行号当作字符游标”的解释，但本轮没有实施修复或另发请求验证。

## 费用与证据

12个一次性传输ticket都已使用一次，12个receipt全部HTTP200且完整，usage已结算；总输入 **41,977 tokens**、总输出 **2,818 tokens**，其中缓存命中17,408、未命中24,569。按高峰、全输入未命中保守核算：

`41,977 × 2 / 1,000,000 + 2,818 × 8 / 1,000,000 = ¥0.106498`

这是费用上界，不是已核对的供应商实扣账单；未使用缓存或空闲时段折扣，**实际账单尚未对账**。请求/回包SHA-256、逐请求usage、调用工具和费用均保存在验收JSON及原SQLite账本。

请求未知预留为0。SQLGlot总账保留17元案例hold用于标记失败批次，**不是额外花费，也不是17元未决请求**；批次已停，余下额度不能自动继续使用。

原始结果目录：
`authority-locbench/6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9/run/`

包含 `stopped.json`、`measurements.json`、`suite.sqlite` 与两题子账、SDK轨迹及已运行三组的result。当前冻结计划与13份旧账本均核验未变。开发日志已追加本次结果和故障证据。

两题均为已曝光开发题，现在Loguru两组、SQLGlot检索组又新增真实模型曝光。只有一题完成配对，且LocAgent实际调用为0；不能据此宣称检索提升/退化或独立测试成绩。后续若处理未知终答字段和读取游标，应先离线分析、另行冻结方案；本轮没有启动修复版，也不会自动重跑。
