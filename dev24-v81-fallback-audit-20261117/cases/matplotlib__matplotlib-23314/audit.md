# matplotlib__matplotlib-23314

原结果：回退；实际源码计量 9771/14336，余 4565 字节；请求 4 次。

[原回答原文（原始provider内容精确提取）](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/matplotlib__matplotlib-23314/raw-answer.txt)；[原始诊断审计](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/matplotlib__matplotlib-23314/locator/diagnostic-audit.json)；[原始provider响应](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-locator-v81-20261117/evidence/run/trial/matplotlib__matplotlib-23314/locator-wire/response-12.json)

[C全部实际工具输出](/Users/xiaomu/Projects/LocAgent-OpenHands/dev24-v81-fallback-audit-20261117/cases/matplotlib__matplotlib-23314/tool-output.txt)

C完整行账本：lib/matplotlib/artist.py:1008-1018; lib/matplotlib/axes/_base.py:3000-3060; lib/matplotlib/widgets.py:2054-2054; lib/matplotlib/widgets.py:2056-2058; lib/matplotlib/widgets.py:2669-2669; lib/matplotlib/widgets.py:2671-2672; lib/matplotlib/widgets.py:2761-2762; lib/mpl_toolkits/mplot3d/axes3d.py:389-444

注意：文件已读范围不自动等于该实体已读范围。未知函数终点不补猜。

## 03-01 R1_body_incomplete_unmarked:lib/matplotlib/axes/_base.py:AxesBase.draw

**边界：限定名错误**。回答事实段写 _AxesBase.draw，候选/推断却写 AxesBase.draw；校验器按不存在或不匹配的完整 ID 检查。实际读取 3000-3060 也不能证明对应 draw 的全部边界。模型命名错误和未读标注问题交织。

原回答片段：
```text
entities 候选：lib/matplotlib/axes/_base.py:AxesBase.draw
L9：- 待验证假设：根因位于 lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw —— 它在调用 super().draw 之前已绘制 patch、pane 和 axis，因此 lib/matplotlib/axes/_base.py:AxesBase.draw 中的可见性短路（3022-3023）来得太晚，无法阻止 3D 背景与坐标轴被绘制。
```

校验器匹配依据：
```json
{
  "entity": "lib/matplotlib/axes/_base.py:AxesBase.draw",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：lib/matplotlib/axes/_base.py:3000-3060；完整实体边界未留存，不把整文件范围当函数覆盖

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 5,
    "path": "lib/matplotlib/axes/_base.py",
    "requested": {
      "cursor": null,
      "end_line": 3060,
      "path": "lib/matplotlib/axes/_base.py",
      "start_line": 3000
    },
    "delivered_metadata": {
      "end_column": 59,
      "end_line": 3060,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 3000,
      "total_lines": 4611
    },
    "cumulative_source_bytes": 9657
  }
]
```

原答中的未读/未核验相关上下文：
```text
L12: 未核验点
L13: - lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw 虽收到 389-444 完整行，但未核验其是否被其他包装（如 figure 级 draw 或 allow_rasterization 装饰器）另行拦截。
L14: - 未读完：lib/matplotlib/widgets.py:ToolLineHandles.set_visible、lib/matplotlib/widgets.py:_SelectorWidget.set_visible（与本问题相关性低，仅作排除）。
L15: - 未核验 Axes3D 是否另有 set_visible 覆写或 _axis3don 相关分支；未运行任何渲染验证。
```

函数长度："未知"

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。

## 03-02 R1_body_incomplete_unmarked:lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw

**边界：装饰器/覆盖口径**。检索元数据给 def 范围 389-444，C 已完整读取；校验器却报正文不完整。policy 把装饰器也纳入范围，检索器从 def 开始，但本地日志未保存原 AST span/388 行，无法确证具体缺口是否仅装饰器或重复定义。

原回答片段：
```text
entities 候选：lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw
L9：- 待验证假设：根因位于 lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw —— 它在调用 super().draw 之前已绘制 patch、pane 和 axis，因此 lib/matplotlib/axes/_base.py:AxesBase.draw 中的可见性短路（3022-3023）来得太晚，无法阻止 3D 背景与坐标轴被绘制。
L13：- lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw 虽收到 389-444 完整行，但未核验其是否被其他包装（如 figure 级 draw 或 allow_rasterization 装饰器）另行拦截。
```

校验器匹配依据：
```json
{
  "entity": "lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw",
  "structured_candidate": true,
  "exact_unread_same_line": false,
  "entity_complete": false,
  "condition": "complete_entity=False 且没有同一行完整ID+字面“未读完”；False具体AST span未持久化"
}
```

校验器按字面路径记账：lib/mpl_toolkits/mplot3d/axes3d.py:389-444；该函数def区间内实际读到：[[389, 444]]

C read_file 请求和实际返回：
```json
[
  {
    "tool_index": 3,
    "path": "lib/mpl_toolkits/mplot3d/axes3d.py",
    "requested": {
      "cursor": null,
      "end_line": 444,
      "path": "lib/mpl_toolkits/mplot3d/axes3d.py",
      "start_line": 389
    },
    "delivered_metadata": {
      "end_column": 30,
      "end_line": 444,
      "next_cursor": null,
      "start_column": 0,
      "start_line": 389,
      "total_lines": 3248
    },
    "cumulative_source_bytes": 6360
  }
]
```

原答中的未读/未核验相关上下文：
```text
L12: 未核验点
L13: - lib/mpl_toolkits/mplot3d/axes3d.py:Axes3D.draw 虽收到 389-444 完整行，但未核验其是否被其他包装（如 figure 级 draw 或 allow_rasterization 装饰器）另行拦截。
L14: - 未读完：lib/matplotlib/widgets.py:ToolLineHandles.set_visible、lib/matplotlib/widgets.py:_SelectorWidget.set_visible（与本问题相关性低，仅作排除）。
L15: - 未核验 Axes3D 是否另有 set_visible 覆写或 _axis3don 相关分支；未运行任何渲染验证。
```

函数长度：{"start": 389, "end": 444, "length": 56, "provenance": "C检索元数据；def至末行，不含装饰器", "definition_excludes_decorators": true}

预算归因：未耗尽14,336总字节；不能将缺口归于总字节上限。可能有4096单页截断、未续读、cursor错误、请求次数结束、所选范围不足或实体身份问题，见原工具记录。
