# 新入口离线验收

通过。dev24全部24题评分数据行按保留键序的JSON序列化逐字相同；实例成员与原manifest相同；make_test_spec输入、run_instance参数、预测对象、超时和资源包装参数逐字相同。评分函数spec_for/evaluate/main源码尾部逐字不变。

验证使用真实原/新数据加载器和拦截harness调用的合成桩，不执行模型、Docker或测试评分；合成resolved=False仅为契约夹具，不是开发集或holdout结果。实际安装和实际容器资源将在开机后、首个付费请求前另核验。

新入口holdout名单50题，SHA-256为5226d5870987a2f9d161b98077aa64788f6e3426d1cea326385694c47922acd6；本验收未解码holdout评分内容。

详见adapter-equivalence.json（24题逐项哈希）、evaluation-adapter.diff、control-validation.json。原57/42冻结文件、Coding Agent、定位器、SDK与harness不改。
