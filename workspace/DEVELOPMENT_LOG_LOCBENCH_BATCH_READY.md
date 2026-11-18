
## 2026-11-13｜LocBench 两题真实批量入口完成离线授权与预算验收

- 新增 `experiments/locbench_batch/{control,live,report,offline_verify}.py`。复用已验证的 LiveSession/单请求传输/SQLite 子账；独立两题授权域 `authority-locbench/`（已忽略），不修改旧六题驱动或原 LocBench 适配。生产授权目录当前不存在。
- 冻结 `locbench_live/v1/manifest.json`，hash `6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9`；原题面/源码/评分冻结 hash 仍为 `45688f8a1c3a705b542d39573fcca9176d1e514edc81114de72f636fc0ddbf1c`。Loguru-1239、SQLGlot-3417 的已曝光开发属性、提交及分组顺序均不变。
- 一次性 24 小时授权绑定全部代码与数据，原子领取阻止重复/并发启动，子授权依赖当前题/组和总账状态。每题17元占用，每请求2.113536元传输前持久化预留；每组4、每题8、共16请求/34元，最坏33.816576元。跨题账本替换、负费用和组序篡改拒绝；无重试/恢复/追加。
- 60 项测试通过（批量16、live16、终答10、预算18）。真实 SDK+LiveSession+账本通过8场景、53次模拟传输：正常16；第二组超时5；收尾继续读8；第二题超时9；截断4；非法finish4；缺finish4；超大回包3。超时/超大回包保留2.113536元未知预留；已收完整但协议错误的调用按usage结算；剩余组保持not_run。超时杀进程组、密钥仅走匿名管道的单测通过。
- 模拟授权仅在verification目录，合成假密钥，真实.env加载器被替换为报错；网络尝试0、供应商请求0、实际费用0。报告强制区分mocked_live_transport，不对脚本答案打分、不称自主调用。1958份历史材料摘要不变。
- 正式锁定SDK1.62.0，deepseek-flash（公开版本DeepSeek-V4.1-Flash-1017），非思考、temperature0、输出2048；2026-11-13公价复核输入未命中2/输出8元每百万。未访问账户/读取密钥，账户实际全包价格尚待确认；别名由供应商维护，启动前需再核对版本。
- 发送范围仅系统/收尾提示、题面、工具定义、当前组源码证据和历史；不发gold/参考补丁/另一组答案。真实入口现已完成，启动只待新范围批准、账户价格/冻结材料/无重复核查及本机TTY中的已有私有.env加载。本阶段未启动、未创建生产grant、不继承旧批准。
- 报告 `LOCBENCH_BATCH_LIVE_READY.md`；机器验收 `verification/LOCBENCH_BATCH_READY_ACCEPTANCE.json`。保留开发曝光、小样本、Python投影、实体ID检索及图重建开销局限，不声明检索收益。

