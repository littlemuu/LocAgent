# 后续两次真实案例：只读核对摘要

2026-11-08 从旧 local-web 目录的输入、result、evidence、run 与账本只读核对。本次整理 **0 次新模型请求**。下列是已有真实 DeepSeek `deepseek-flash` 运行，不是离线 demo，也不等于系统评测。原始运行目录没有复制进演示包。

## 1. itsdangerous：时间戳验证和过期检查

- 仓库：[pallets/itsdangerous](https://github.com/pallets/itsdangerous/tree/672971d66a2ef9f85151e53283113f33d642dabd)。固定 commit：`672971d66a2ef9f85151e53283113f33d642dabd`。
- 问题：`Where are signed timestamped values verified and checked for expiration?`
- 结果包含 `TimestampSigner.unsign` 和 `TimestampSigner.validate`，还返回其他函数和共 3 个文件。不能描述成只选了唯一正确函数。
- 3 个 HTTP 200 请求，均 settled；run/result success，账本 finished。
- 原始 usage 汇总：14,664 prompt + 433 completion tokens。按当时本地配置价格核算 CNY 0.032792，**不是供应商账单，也不是未来价格承诺**。

## 2. nano-vllm：取消的核心函数

- 仓库：[littlemuu/nano-vllm](https://github.com/littlemuu/nano-vllm/tree/5948237109de55810b8b9f79410c95db1dbbc3f6)。固定 commit：`5948237109de55810b8b9f79410c95db1dbbc3f6`。
- 问题：`取消的核心函数是哪一个？`
- 结果包含 [`Scheduler.cancel`，42–62 行](https://github.com/littlemuu/nano-vllm/blob/5948237109de55810b8b9f79410c95db1dbbc3f6/nanovllm/engine/scheduler.py#L42-L62)，另含 `scripts/demo_cancellation_cpu.py:run_policy`，共 5 个文件。
- 3 个 HTTP 200 请求，均 settled；run/result success，账本 finished。
- 原始 usage 汇总：16,074 prompt + 388 completion tokens。本地核算 CNY 0.035252，不等于供应商账单。
- 实际使用了 `read_tool_output` 续读检索输出，但最后实体读取仍被总工具预算截断。不能宣称全部证据完整读完。

## 可以和不可以得出的结论

可以说明真实 provider 路径运行过、工具循环完成过、输出位置能够回到固定版本源码核对。`quality_evaluated=false`：没有足够样本、统一标注或对照实验支持泛化准确率。

不能由两例推断：任意问题都能命中、构造读取补丁有效、成本固定、空缓存安装成功、每次都会完成，或旧未知请求未计费。另有旧未知任务仍原地保留，没有重试或抹除。

早期文档里的 `pallets/itsdangerous@2.2.0`（`096c8d...`）是免费 prepare，**不是本页后续真实案例 commit**。旧 DB fake preview 固定空结果、CLI/web 合成 demo 的 `demo.py:render` 和本页案例也不能混为一谈。

## 维护者本机追溯

旧 local-web 的任务编号分别是 `82a30981580542d3b3654c7b983abd78` 与 `d6df379e4fe8470eb7315bb2ad65626c`。只在可信本机查看；不要分享整个目录、授权、响应或 key。此说明只列公开仓库问题与结果摘要。
