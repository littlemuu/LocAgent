# pydata__xarray-4094

原结果：回退；实际源码计量 9703/14336，余 4633 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pydata__xarray-4094/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pydata__xarray-4094/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/pydata__xarray-4094/locator-wire/response-35.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/pydata__xarray-4094/tool-output.txt)

C完整行账本：xarray/core/dataarray.py:1895-1990; xarray/core/dataset.py:3370-3470

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 09-01 R4_citation_not_delivered:xarray/tests/test_dataset.py:3033-3055

**边界：稀疏搜索连成范围**。只有3033/3040/3044/3048/3055等搜索行，存在相关测试的说法有依据并明确未读正文；但3033-3055不是连续读取。是否接受“搜索命中范围”需政策明确。

原回答片段：
```text
L6：- xarray/tests/test_dataset.py:3033-3055、xarray/tests/test_dataarray.py:2132-2135：存在 roundtrip 与 ValueError 测试（仅搜索命中，未读正文）。
L15：- 未读 xarray/tests/test_dataset.py:3033-3055 与 xarray/tests/test_dataarray.py:2132-2135 正文，测试覆盖情况未知。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "xarray/tests/test_dataset.py:3033-3055",
  "path": "xarray/tests/test_dataset.py",
  "start": 3033,
  "end": 3055
}
```

校验器按字面路径记账：无；另有实际搜索行：3033,3040,3044,3048,3055

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "xarray/tests/test_dataset.py",
    "line": 3033,
    "text": "    def test_to_stacked_array_to_unstacked_dataset(self):"
  },
  {
    "tool_index": 1,
    "path": "xarray/tests/test_dataset.py",
    "line": 3040,
    "text": "        x = y.to_unstacked_dataset(\"features\")"
  },
  {
    "tool_index": 1,
    "path": "xarray/tests/test_dataset.py",
    "line": 3044,
    "text": "        x0 = y[0].to_unstacked_dataset(\"features\")"
  },
  {
    "tool_index": 1,
    "path": "xarray/tests/test_dataset.py",
    "line": 3048,
    "text": "    def test_to_stacked_array_to_unstacked_dataset_different_dimension(self):"
  },
  {
    "tool_index": 1,
    "path": "xarray/tests/test_dataset.py",
    "line": 3055,
    "text": "        x = y.to_unstacked_dataset(\"features\")"
  }
]
```

## 09-02 R4_citation_not_delivered:xarray/tests/test_dataarray.py:2132-2135

**边界：稀疏搜索连成范围**。只收到2132和2135搜索行；测试名称支持 ValueError 用例存在，原文承认未读正文，但引用2132-2135连续范围不满足字面覆盖规则。

原回答片段：
```text
L6：- xarray/tests/test_dataset.py:3033-3055、xarray/tests/test_dataarray.py:2132-2135：存在 roundtrip 与 ValueError 测试（仅搜索命中，未读正文）。
L15：- 未读 xarray/tests/test_dataset.py:3033-3055 与 xarray/tests/test_dataarray.py:2132-2135 正文，测试覆盖情况未知。
```

校验器匹配依据：
```json
{
  "regex": "(?P<path>[\\w./-]+\\.py):(?P<start>\\d+)(?:[-–](?P<end>\\d+))?",
  "citation": "xarray/tests/test_dataarray.py:2132-2135",
  "path": "xarray/tests/test_dataarray.py",
  "start": 2132,
  "end": 2135
}
```

校验器按字面路径记账：无；另有实际搜索行：2132,2135

C read_file 请求和实际返回：
```json
[]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "xarray/tests/test_dataarray.py",
    "line": 2132,
    "text": "    def test_to_unstacked_dataset_raises_value_error(self):"
  },
  {
    "tool_index": 1,
    "path": "xarray/tests/test_dataarray.py",
    "line": 2135,
    "text": "            data.to_unstacked_dataset(\"x\", 0)"
  }
]
```

## 09-03 R1_body_incomplete_unmarked:xarray/core/dataset.py:Dataset.to_stacked_array

**边界：真实函数终点缺证**。C读3370-3470，末尾仅到嵌套 ensure_stackable 定义，未提供外层函数未读标注；audit称不完整。但日志没有该实体完整AST范围或后续原源码，不能独立排除装饰器/边界口径原因；不据缺失元数据断言真违规。

原回答片段：
```text
entities 候选：xarray/core/dataset.py:Dataset.to_stacked_array
L11：- 待验证假设：`xarray/core/dataset.py:Dataset.to_stacked_array` 的 `assign_coords[dim] = None` 使单维变量在 stacking dim 上产生 NaN 坐标，是 roundtrip 中坐标冲突的上游来源之一。
```

校验器匹配依据：
```json
{
  "entity": "xarray/core/dataset.py:Dataset.to_stacked_array",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：xarray/core/dataset.py:3370-3470；完整实体边界未留存，不把整文件范围当函数覆盖；另有实际搜索行：3410,3370

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 4,
    "path": "xarray/core/dataset.py",
    "requested": {
      "cursor": null,
      "end_line": 3470,
      "path": "xarray/core/dataset.py",
      "start_line": 3370
    },
    "delivered_metadata": {
      "end_column": 41,
      "end_line": 3461,
      "next_cursor": "rf1_f371c96a1a4e5a9385e1f1b23628cb72dc3772ec7f3542d43fda4f74676f2221",
      "start_column": 0,
      "start_line": 3370,
      "total_lines": 6372
    },
    "cumulative_source_bytes": 9240
  },
  {
    "tool_index": 5,
    "path": "xarray/core/dataset.py",
    "requested": {
      "cursor": "rf1_f371c96a1a4e5a9385e1f1b23628cb72dc3772ec7f3542d43fda4f74676f2221",
      "end_line": null,
      "path": "xarray/core/dataset.py",
      "start_line": null
    },
    "delivered_metadata": {
      "end_column": 0,
      "end_line": 3470,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 3462,
      "total_lines": 6372
    },
    "cumulative_source_bytes": 9703
  }
]
```

实际搜索原文（仅作已交付片段，不自动认定函数完整）：
```json
[
  {
    "tool_index": 1,
    "path": "xarray/core/dataset.py",
    "line": 3410,
    "text": "        DataArray.to_unstacked_dataset"
  },
  {
    "tool_index": 2,
    "path": "xarray/core/dataset.py",
    "line": 3370,
    "text": "    def to_stacked_array("
  }
]
```

原答中的未读/未核验相关上下文：
```text
L6: - xarray/tests/test_dataset.py:3033-3055、xarray/tests/test_dataarray.py:2132-2135：存在 roundtrip 与 ValueError 测试（仅搜索命中，未读正文）。
L13: 未核验点
L14: - 未读 `Dataset.__init__`/merge 逻辑，无法确认冲突具体发生在哪个坐标变量上。
L15: - 未读 xarray/tests/test_dataset.py:3033-3055 与 xarray/tests/test_dataarray.py:2132-2135 正文，测试覆盖情况未知。
```

函数长度："未知"

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。
