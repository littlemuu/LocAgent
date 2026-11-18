
## 2026-11-12｜六题批准试跑：首题 finish 输出截断后停止

- 用户明确批准六题最多48次DeepSeek请求、总上限102元后，复核官方价格2/8元每百万tokens、同一既有私有.env元数据、冻结hash d172860a…及无重复启动，登记并领取一次性套件授权，运行一次。未显示或复制Key。
- d01_cache基础组进行了4次真实请求，前3次执行list_files×1、search_text(cache)×1、read_file×6，读取全部6文件；源码返回累计2915字节，耗时15.719秒。
- 第4次仅提供并指定finish；供应商实际返回finish但finish_reason=length、completion_tokens=1024。适配器以model_output_truncated拒绝，无有效终答。整套停止，无自动重试、补答或续跑。
- 基础组1失败5未运行；检索组6未运行；完成配对0。不能说模型未自主选择检索，也不能比较检索收益。盲评包为空；失败0分与未运行空分分开记录。
- 4次HTTP200 usage均已结算，输入7307/输出1476tokens；保守费用上界0.026422元，无待结请求预留。外层17元为首题本地预算占用，不是扣款，实扣尚未与供应商账单核对。剩余44次没有使用，授权已消耗。
- 停止后只读审计确认冻结代码/题目/评分未变，五个历史真实账本哈希未变；新增d01暴露记录，不改旧冻结快照。未修改运行代码或创建新授权。
- 交付DEV_BATCH_LIVE_RESULT.md、verification/DEV_BATCH_LIVE_INCIDENT.json、verification/DEV_BATCH_EXPOSURE_DELTA.json及原始批次measurements/stopped/receipt/SDK轨迹。下一步可离线检查终答长度与格式；更改输出上限需重算预算、重新冻结并另获试跑授权。
