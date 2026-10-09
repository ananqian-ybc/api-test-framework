# AGENTS.md —— 项目约定（给协作者与后续会话）

本文件是进入本仓库的**第一入口**。恢复工作前按顺序读：
本文件 → `tasks/todo.md` → `tasks/lessons.md` → 最近 git log。

## 项目定位

游戏服务端接口自动化测试框架 + 自带被测服务（SUT）。
使用者目标：**游戏测试岗求职作品**。因此代码可读性、可演示性、面试可讲性
与正确性同等重要。

## 环境与命令（Windows PowerShell）

```powershell
# 依赖已锁定，装在项目内 .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 全量回归（自动拉起被测服务，随机端口）
.venv\Scripts\python.exe -m pytest

# 冒烟 / 反例 / 并发
.venv\Scripts\python.exe -m pytest -m smoke
.venv\Scripts\python.exe -m pytest -m negative
.venv\Scripts\python.exe -m pytest -n 4

# 独立工具
.venv\Scripts\python.exe scripts\smoke_mock_server.py
.venv\Scripts\python.exe scripts\verify_gacha_probability.py --draws 10000
.venv\Scripts\python.exe scripts\verify_damage_formula.py
```

中文输出乱码时先设置：`$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'`。
`pytest` 没有 `--no-html` 参数（本仓库 addopts 已内置 pytest-html）。

## 分层红线

| 层 | 规则 |
|---|---|
| `mock_server/rules.py` | 数值与概率规则的**唯一权威来源**；纯函数，必须可单测 |
| `mock_server/store.py` | 只管游戏规则，**不碰 HTTP**；违反规则抛 `DomainError(code, message, http_status)` |
| `mock_server/app.py` | HTTP 层：路由 + 鉴权 + 入参校验 + 统一响应；状态码语义见 README 第 4 节 |
| `common/` | **不得出现任何游戏领域概念**（角色/抽卡/背包等）。领域化改造只允许改 SUT 与用例层 |
| `testcases/` | 只写业务断言，不拼 Token、不硬编码地址、不写 sleep |
| `data/` | 数值表与用例数据；期望值必须**独立得出**，禁止由被测代码生成 |

## 硬性约定

1. **随机必须可复现**：任何引入随机的接口都要支持 `seed`，并有用例证明同 seed 结果一致。
2. **数值期望值独立来源**：`data/battle_damage_cases.yaml` 的期望值手算或由脚本独立实现得出；
   `scripts/verify_damage_formula.py` 必须保留独立实现（不得 import `rules.py` 的公式）。
3. **用例数据隔离**：游戏域用例统一用 `player` / `make_player` fixture（每用例独立账号），
   禁止共用账号写有副作用的用例。
4. **失败必须无副作用**：所有拒绝类用例都要断言"失败请求没有改变服务端状态"。
5. **测试先行**：新增行为先写失败测试并确认失败原因正确（不是语法/导入错误），再实现。
6. **发现 bug 必须固化为回归测试**，并在 `tasks/lessons.md` 记录现象/根因/修复。
7. 单文件 ≤ 400 行、函数 ≤ 40 行、嵌套 ≤ 3 层；所有函数签名带类型标注。
8. 提交信息用 `<type>(<scope>): <description>`，祈使句、小写、≤72 字符。

## 完成定义（DoD）

- [ ] 用例全绿（含 `-n 4`）
- [ ] `scripts/smoke_mock_server.py` 全通过（改了 SUT 时必跑）
- [ ] 改了数值/概率规则时，同时更新 `data/*.yaml` 期望值与 README 公示规则
- [ ] 新增接口同步更新 README 接口清单与状态码约定
- [ ] `tasks/todo.md` 勾选进度，`tasks/lessons.md` 记录新坑
- [ ] 不留未提交改动

## 反目标（本仓库明确不做）

- 不引入 UI 自动化（Selenium/Airtest）、性能压测（JMeter）、长连接协议
  —— 这些属于客户端/专项方向，另行立项
- 不做无用的目录预留：当前用例直接经 `ApiClient` 编写，等用例规模真的需要时才抽出接口封装层
