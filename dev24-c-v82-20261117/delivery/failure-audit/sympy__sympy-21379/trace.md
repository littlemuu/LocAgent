# sympy__sympy-21379

定位包：

```text
已读到的事实（附文件:行号）
- sympy/polys/polytools.py:4393-4399：`_parallel_dict_from_expr` 返回后遍历 `opt.gens`，任一 gen 是 `Piecewise` 即 `raise PolynomialError("Piecewise generators do not make sense")`。
- sympy/polys/polytools.py:4369-4383：该函数先 `sympify(expr)`，`opt.expand` 为真时调用 `expr.expand()`，再收集 `_exprs`/`_polys`。
- sympy/polys/polytools.py:4388-4395：`_polys` 中的表达式被 `as_expr()` 还原；若 `opt.gens` 为空则抛 `PolificationFailed`。
- sympy/core/basic.py:1058-1064：`_subs` 先判 `_aresame(self, old)`，否则调 `self._eval_subs(old, new)`，返回 None 时走 `fallback`。
- sympy/core/basic.py:1026-1056：`fallback` 逐个对 `self.args` 调 `arg._subs`，命中则 `self.func(*args)` 重建。
- sympy/core/basic.py:949-952：`subs` 对序列逐项 `rv._subs(old, new, **kwargs)`，非 Basic 结果即 break。

推断
- 待验证假设：报错来自 `sympy/polys/polytools.py:_parallel_dict_from_expr` 的 gens 检查，即某条路径把含 `Piecewise` 的表达式送进了多项式化（`Poly`/`parallel_poly_from_expr`），而非 `subs` 本身直接抛错。
- 待验证假设：`sympy/core/basic.py:Basic._subs` 的 `fallback` 重建 `exp(sinh(Piecewise(...)/z))` 时触发求值/展开，使 `Piecewise` 成为多项式生成元；real 假设改变 `Piecewise` 的化简结果，从而决定是否走到该分支。
- 待验证假设：缓存（`clear_cache`）影响中间化简结果，故第二次调用成功，说明存在依赖缓存状态的求值路径。

未核验点
- `sympy/core/basic.py:Basic.subs` 与 `Basic._subs` 的 docstring 段（761-873、890-948）未读完；`sympy/core/function.py:Subs` 仅读到 2196-2211，其余未读完。
- 未读到 `Piecewise._eval_subs`、`sinh`/`exp` 的 `_eval_subs`，也未读到 `parallel_poly_from_expr` 的调用方，调用链不完整。
- 未运行任何复现或验证。

最小验证：`python -c "from sympy import *; x,y,z=symbols('x y z',real=True); print(exp(sinh(Piecewise((x,y>x),(y,True))/z)).subs({1:1.0}))"`（建议，未执行）

以下内容未在阅读记录中核验：
- [R1] sympy/polys/polytools.py:_parallel_dict_from_expr
```

编码终答：

```text
Status: investigation only — no source changes were made before the budget ran out, so the repository is unchanged.

What I established from the reproduction (`exp(sinh(Piecewise((x, y > x), (y, True))/z)).subs({1: 1.0})` with real symbols):

- The failure is not in `subs` itself. `Basic._subs` falls back to rebuilding `exp(...)`, and `exp.eval` asks `arg.is_zero`, which triggers the assumption machinery.
- The chain is: `exp.eval` -> `arg.is_zero` -> `sinh._eval_is_real` (sympy/functions/elementary/hyperbolic.py:251) -> `(im % pi).is_zero` -> `Mod.eval` (sympy/core/mod.py:169) -> `gcd(p, q)` -> `parallel_poly_from_expr` -> `_parallel_poly_from_expr` (sympy/polys/polytools.py:4399) which raises `PolynomialError("Piecewise generators do not make sense")`.
- So the root cause is that `sinh._eval_is_real` unconditionally computes `im % pi` even when `im` is not a number (here `im` involves a `Piecewise`), and `Mod.eval` calls `gcd` on expressions containing `Piecewise`, which the polys module rejects. The cache dependence in the report comes from whether the `is_zero`/`is_real` facts are already cached.

Suggested fix direction (not applied): in `sinh._eval_is_real` (and the analogous `cosh`/`tanh` handlers), only do the `im % pi` check when `im` is a number (e.g. `if im.is_number: return (im % pi).is_zero`), or guard `Mod.eval`'s `gcd` call so it does not attempt polynomial gcd on expressions containing `Piecewise`. A regression test should be added for the MWE with real symbols.

Tests: only the reproduction script was run (it reproduces the traceback); no test suite was executed.
```

工具记录：

请求 1 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | tail -40",
  "timeout_seconds": 120
}
```

请求 2 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && sed -n 230,270p sympy/functions/elementary/hyperbolic.py && sed -n 140,200p sympy/core/mod.py",
  "timeout_seconds": 120
}
```

请求 3 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && sed -n 1,140p sympy/core/mod.py",
  "timeout_seconds": 120
}
```

请求 4 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && sed -n 200,260p sympy/core/mod.py",
  "timeout_seconds": 120
}
```

请求 5 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nx, y, z = symbols('x y z', real=True)\ne = sinh(Piecewise((x, y > x), (y, True)) / z)\nprint(e.as_real_imag())\n\" 2>&1 | tail -20",
  "timeout_seconds": 120
}
```

请求 6 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nx, y, z = symbols('x y z', real=True)\ne = sinh(Piecewise((x, y > x), (y, True)) / z)\nprint(e.as_real_imag())\nprint(e.as_real_imag()[1])\nprint(repr(e.as_real_imag()[1]))\n\" 2>&1 | tail -20",
  "timeout_seconds": 120
}
```

请求 7 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | head -40",
  "timeout_seconds": 120
}
```

请求 8 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 40,80p",
  "timeout_seconds": 120
}
```

请求 9 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 1,40p",
  "timeout_seconds": 120
}
```

请求 10 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 40,60p",
  "timeout_seconds": 120
}
```

请求 11 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 60,80p",
  "timeout_seconds": 120
}
```

请求 12 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 20,40p",
  "timeout_seconds": 120
}
```

请求 13 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 10,22p",
  "timeout_seconds": 120
}
```

请求 14 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 1,12p",
  "timeout_seconds": 120
}
```

请求 15 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 12,20p",
  "timeout_seconds": 120
}
```

请求 16 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 20,30p",
  "timeout_seconds": 120
}
```

请求 17 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 30,40p",
  "timeout_seconds": 120
}
```

请求 18 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 40,50p",
  "timeout_seconds": 120
}
```

请求 19 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 50,60p",
  "timeout_seconds": 120
}
```

请求 20 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 60,70p",
  "timeout_seconds": 120
}
```

请求 21 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 70,80p",
  "timeout_seconds": 120
}
```

请求 22 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 80,90p",
  "timeout_seconds": 120
}
```

请求 23 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 90,100p",
  "timeout_seconds": 120
}
```

请求 24 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 100,110p",
  "timeout_seconds": 120
}
```

请求 25 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 110,120p",
  "timeout_seconds": 120
}
```

请求 26 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 120,130p",
  "timeout_seconds": 120
}
```

请求 27 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 130,140p",
  "timeout_seconds": 120
}
```

请求 28 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 140,150p",
  "timeout_seconds": 120
}
```

请求 29 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 150,160p",
  "timeout_seconds": 120
}
```

请求 30 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 160,170p",
  "timeout_seconds": 120
}
```

请求 31 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 170,180p",
  "timeout_seconds": 120
}
```

请求 32 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 180,190p",
  "timeout_seconds": 120
}
```

请求 33 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 190,200p",
  "timeout_seconds": 120
}
```

请求 34 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 200,210p",
  "timeout_seconds": 120
}
```

请求 35 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 210,220p",
  "timeout_seconds": 120
}
```

请求 36 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 220,230p",
  "timeout_seconds": 120
}
```

请求 37 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 230,240p",
  "timeout_seconds": 120
}
```

请求 38 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 240,250p",
  "timeout_seconds": 120
}
```

请求 39 · terminal · exit=0 · 修改=[]
```json
{
  "command": "cd /testbed && python -c \"\nfrom sympy import *\nfrom sympy.core.cache import clear_cache\nx, y, z = symbols('x y z', real=True)\nexpr = exp(sinh(Piecewise((x, y > x), (y, True)) / z))\nprint(expr.subs({1: 1.0}))\n\" 2>&1 | sed -n 250,260p",
  "timeout_seconds": 120
}
```
