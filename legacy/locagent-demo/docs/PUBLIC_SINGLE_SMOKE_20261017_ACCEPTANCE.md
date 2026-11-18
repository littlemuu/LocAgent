# 当前 engine 单题真实服务验收：2026-10-17

**通过：公开 URL→新静态准备→当前 engine 清单→一次性授权→API/worker→DeepSeek→可查询结果。** 执行代码 HEAD `eee52a4d1420c9bbea232f42b9bea615741559d9`；后续仅文档提交，不改变 engine 绑定。此记录补齐当前版本的单题真实服务证据，不是完整定位质量评测，也不修复独立 pgvector 并发缺陷。

## 明确授权与固定范围

用户消息 `Sentinel_3baafe7156fc819180fbd12d59b0ba84` 同意本题的接收方、公开数据、最多3次调用、单次attempt、独立7元预算。此 ID 是授权消息引用，不是凭据。未新建账号凭据，既有 key 仅供本次 worker 环境使用，不保存或展示。只加载指定 key，不输出完整 env。

- 仓库 `https://github.com/pallets/itsdangerous`，commit `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd`。
- 问题：Where does the library reject an expired signed value when a maximum age is supplied?
- 接收方 `https://api.deepseek.com/chat/completions`，请求/响应模型均精确 `deepseek-flash`。
- 数据为公开问题、仓库标识、系统和工具提示、检索到的公开源码与工具历史，不发送秘密或 gold。没有执行下载仓库的安装脚本、测试或项目代码。
- `thinking={"type":"disabled"}`、temperature=0、stream=false、max_tokens=1024、max_calls=3；单题一次attempt，不自动重试；HTTP 60秒，任务300秒，请求体65536 bytes上限。

价格来源：[DeepSeek 官方价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)，父任务2026-10-17 03:20 UTC核验，本轮执行前再次读取一致：Flash对应V4.1-Flash，上下文标注1M，高峰未缓存输入2元/百万、输出8元/百万。预留1,048,576 tokens覆盖十进制1M并等于二进制1Mi；每次完整预留2.105344元，三次6.316032元≤7元。没有因空闲费率或缓存折扣减少预留。思考模式指南页面抓取超时；实际序列化离线检查通过，历史同参数兼容且本次3次响应均通过合同验证。

## 执行身份

| 项目 | 值 |
|---|---|
| 新静态任务 | `9419be40-105f-491b-8272-d229fd414d4f`，completed，attempt1 |
| 新静态源 | `prepared-114e823140a2ccc58dff91bd6337d8c2c251b33abe825f05ec756742595af79f` |
| 本次计划/授权 SHA256 | `feabf75ac675c8add3fb910c012ecf70e37de563ccd77f7a9bb43b716b273e13` |
| 真实任务 | `da3a7576-c848-4dc2-ae6c-21caca51e759`，completed，attempt1，result success |
| 当前完整 engine 哈希 | 与本次源清单完全一致 |
| 索引缓存 | 新目录、cache_hit=false，未复用旧源清单或旧授权 |

runner 依次启动新隔离 PostgreSQL、运行新 schema 初始化、启动 API/worker 提交静态任务；完成后验证源和计划，再以已有明确授权生成一次性实验授权并提交真实任务。计划哈希生成后没有扩大授权范围。静态阶段没有模型请求，真实阶段只有下列3次。

## 原始响应与预算结算

| 调用 | HTTP/状态 | 输入tokens | 输出tokens | 高峰核算元 |
|---|---|---:|---:|---:|
| 0 | 200 / settled | 3461 | 138 | 0.008026 |
| 1 | 200 / settled | 5207 | 58 | 0.010878 |
| 2 | 200 / settled | 5229 | 149 | 0.011650 |
| 合计 | 3次、无重试/unknown | 13897 | 345 | **0.030554** |

全部返回模型精确匹配、request ID非空、原始响应完整且SHA与账本一致。账本 `finished=true`、`halted=false`、`reserved=0`，任务身份绑定正确。记录的是实际响应usage经批准高峰费率计算并持久结算的金额；未查询控制台账单，不能称实际现金扣款0.030554元。旧账本、unknown及旧预算未调整。

请求SHA256依次为：

```text
39a138b97dd469f326464471c254d3e4918a5b43954ec8b8f5f8bb84dd930899
57bc9e2fd51d2e600126046219337ff8b0d5a54b0c6d6494bd444a1fa8c011d1
71425e7a0e2c00844ee72e0da2fd5569911475c24c45efc5002dbdace6740561
```

原始响应SHA256依次为：

```text
3177885510ffe2222a3953dee517d71b6bffe1f6aab2070a378a35f3f353b7b5
1c2549cd303ec3465e6ccfdd739bf6d042d065822362d024f4db8533b0eba7c3
80cf727fa60c25dc9ee5268eedc552ef139f013c35eb7a0c0cad7664b9225aa2
```

## 定位核验与限制

返回 `src/itsdangerous/timed.py:TimestampSigner.unsign` 及 `TimestampSigner.validate`。手工检查固定commit源码：138–146行在提供max_age时计算age，age>max_age即抛SignatureExpired，直接对应问题；160–167行validate包装unsign调用。另返回exc.py、serializer.py、url_safe.py，结果范围比最小答案宽。这里是单题语义验收，不计算或声称总体准确率。工具返回曾受字节上限截断，证据中保留；本次目标判断代码可见。

## 隔离与清理

容器 `locagent-public-single-20261017`，独立卷同名加`-data`，固定本地已有PostgreSQL镜像SHA256 `328b1c9542f2a29c053407748d06f0e4de82b8e2c94249d5f1599b2f5342e1e6`，未拉取镜像。仅loopback数据库55442/API18092，数据库public_single，schema `public_preview_single_20261017`。未操作原demo或先前pgvector数据库。

自有API/worker均已结束、容器exited，结束核验55442和18092无监听。新数据卷、schema、索引、授权和证据保留。3205个保护文件哈希不变，覆盖旧单题证据、冻结实验/账本及原学习README。Python子进程和资源限制不等同完整沙箱，仍不声称可安全公网部署。

## 证据与剩余事项

本地目录 `outputs/public-single-20261017/`（ignored）：`operator-runner.py`、`plan-review.json`、静态和真实提交/任务/attempts、`public-summary.json`、完整审计、原始响应及账本、`cleanup.json`。操作命令为已有venv执行本次独占目录runner，禁止重复执行或删除目录以重跑。

本轮仅新增验收文档，无产品实现变更；未push/merge。pgvector仍为16通过1错误，须另修并发领取的复合唯一约束竞争。dense/hybrid未接入公开HTTP任务，expanded50仍仅为检索实验。本题补验不能覆盖这些限制。
