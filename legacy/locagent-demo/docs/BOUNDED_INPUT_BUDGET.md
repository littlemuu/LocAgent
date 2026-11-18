# 单题 DeepSeek 文本输入预算上界

新增显式 `input_bound="deepseek-v41-text-20261101"`、`input_token_cap=131072`。
默认仍是 `full-context`，不能在该默认模式下偷偷设置更小的输入 cap。
新模式只覆盖这次已核验的 DeepSeek Flash 文本/本地函数工具协议，不是通用 token 估算器。

## 证明与限制

2026-11-01 核验的官方模型是 `deepseek-flash` / `DeepSeek-V4.1-Flash-1017`。
公开编码参考固定在仓库修订 `314113f8a7dadb388215396ba5fbee2c610a04d6`：

- [encoding.py](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/314113f8a7dadb388215396ba5fbee2c610a04d6/encoding/encoding.py)：37962 bytes，SHA256 `13231c592e958fb39e2af6001dae69d90e7a36b265702b9b390236fb387599e2`。只用 AST 提取常量，未执行参考代码。空工具说明模板的 UTF-8 长度为 983 bytes；已检查的固定标记/包装常量最大 97 bytes。
- [tokenizer.json](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/314113f8a7dadb388215396ba5fbee2c610a04d6/tokenizer.json)：只读取元数据前缀，未下载权重或使用词表。1 MiB 前缀 SHA256 `462d744d52ec66501066d2fadcd5e25e2706dcae6518d7c45b1c54f785016be0`。normalizer 为无操作 Sequence；预处理为 Split 分割后 ByteLevel，`add_prefix_space=false`；模型为 BPE。ByteLevel 后处理只处理偏移，不加入文本 token。
- [官方协议转换与 tokenizer 说明](https://github.com/deepseek-ai/deepseek-recipe/blob/main/docs/tokenizer.md)区分显式特殊 token 与用户输入的同名字面文本。本上界把两者都按其完整 UTF-8 长度收费，不把用户输入特殊标记当作一个便宜 token。

令 B 为**最终发送 JSON bytes**长度；M 为消息数，T 为工具定义数，C 为历史函数调用数，A 为这些调用的顶层参数总数。
对允许的请求形状，保守输入上界为：

```
U = 2 * B + 8192 + 512 * (M + T + C + A)
```

证明范围：

1. 消息只允许字符串文本（assistant 可为 null），工具只允许本地 function schema，历史参数必须直接解码成 JSON 对象。禁止图片/附件/服务端工具、命名空间、未知形状、额外消息前缀、stop/response-format、浮点数、超大整数和过深 JSON。图片控制标记也拒绝。
2. 模板中的变量字符串/工具 schema/参数来自 wire JSON。字符串解码不会增长 UTF-8 长度；默认 JSON 重排增加的空格不超过原标点数量，因此 `2B` 覆盖文本及重排。禁止浮点数避免 `1e15` 被重新序列化成更长小数；禁止二次编码的参数避免未审查的解释分支。
3. 模板固定工具说明、首尾标记和强制函数选择支架计入 8192；逐消息/工具/调用/参数的包装各按 512 bytes 计入。变量长度已在 B 内。工具消息合并、工具结果排序不会复制其内容。这个范围只适用于上述固定参考协议，不能直接套用于别的模型或协议。
4. 无扩张 normalizer、无前缀空格的字节级 BPE，每个普通文本 token 至少消耗一个字节；合并只减少 token 数。显式特殊标记按字面完整字节计也只会高估。因此该文本协议的输入 token 数不超过 U。

在 POST 前验证 B ≤ 32768 且 U ≤ `input_token_cap` ≤ 131072。超过限制或证明不适用时直接拒绝；**不自动截断问题、源码或工具历史，也不静默回退到另一个 provider**。

这依赖官方当前公开的编码/计费合同，与输出 `max_tokens` 和单价的保证一样，不能约束供应商后台违反合同。API 模型名是可变别名，因此本次 profile 只允许 2026-11-01 UTC 当天发新请求；2026-11-02 00:00 UTC 起保守拒绝，重新核验版本后才能更新 profile。旧请求证据在过期后仍可审计。未声称已通过真实服务 token 对照或真实定位验收。

## 金额和调用次数

保留真实模型 `context_tokens=1048576`；新字段表示经过验证的**本次输入上限**，不会谎报模型 context。
该 profile 强制非思考、非流式、指定官方 HTTPS endpoint/model、最多 1024 输出 tokens、最多 3 次调用、CNY 币种、总预算不超过 1 元；输入和输出费率不得低于核验的高峰未缓存价格 2/8 元每百万。

输入 cap 131072、输出 cap 1024 时，每次持久预留：

```
(131072 * 2 + 1024 * 8) / 1000000 = 0.270336 元
3 次全额预留 = 0.811008 元 ≤ 1 元
```

每次仍在同一个账本锁下检查“已结算 + 未结算 + 下次满额预留 ≤ 批准总额”和累计调用数。只按原始响应整数 usage 结算，全部输入按未缓存高峰价计；没有利用折扣增加额度。较低预算可能提前阻止下次调用。

最终请求 bytes 在私有授权目录中的独立不可变 body store 落盘；账本记录其 hash、长度与输入上界证据。每次重验账本都重新读取请求、验 hash、重算证明，并核验已结算原始响应。任何篡改、usage 超过 U、超时、非 200、不完整响应或响应落盘失败都停止执行；未知结果保留整笔预留，不能重试或换执行器复用授权。请求证据写入失败会在 POST 前停止；孤立证据文件也不会被覆盖。

原有 SSRF/global-address 检查、TLS 固定目标、无代理/重定向/网络重试、一次性授权、task fencing、幂等和数据库恢复策略未放松。新的 profile/输入 cap/完整 engine 文件都进入计划绑定；旧授权不能复用。

## 离线验证

`tests/test_bounded_input_budget.py` 使用原始响应 stub，不调用真实模型。覆盖 UTF-8 字节上限、较小 wire/较大 DSML 展开、未知/多模态形状、强制 finish、无截断、持久化顺序、连续和并发调用的共享额度、未知结果保留预留与禁止重试、证据篡改、过期和计划绑定。原 `test_public_authorization.py` 继续验证默认路径。

```sh
TMPDIR=/private/tmp .venv/bin/python -B -m unittest discover -s tests -p 'test_*input_budget.py' -v
TMPDIR=/private/tmp .venv/bin/python -B -m unittest discover -s tests -p test_public_authorization.py -v
```

本次真实输入/缓存尚需在最终 engine 代码下重新准备；测试通过不等于已联网调用或定位成功。
