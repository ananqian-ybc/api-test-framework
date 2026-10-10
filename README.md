# 游戏服务端接口自动化测试框架

![api-test](https://github.com/ananqian-ybc/api-test-framework/actions/workflows/api-test.yml/badge.svg)

> 分层、可离线跑通、可接 CI 的**游戏服务端接口 + 数值/概率**自动化测试项目，
> 自带一个可复现的被测服务（stdlib 实现，零第三方依赖），clone 下来一条命令即可跑出报告。

**当前规模**：136 条自动化用例（游戏域 78 + 框架自测 58）｜11 个被测接口｜
10000 抽概率统计检验 + 587 组伤害数值批量校验｜`-n 4` 并发 4.8s 跑完。

---

## 1. 为什么做这个

游戏测试岗的核心要求是三件事：**接口/协议测试能力**、**数值与概率验证能力**、
**可重复执行的自动化回归**。本项目把这三件事都做成可演示的实物：

| 岗位要求 | 本项目对应产出 |
|---|---|
| 接口测试 | 11 个游戏服务端接口的分层自动化框架 |
| 数值验证 | 伤害公式批量校验脚本（576 组边界网格 + 独立复算） |
| 概率验证 | 抽卡 10000 次卡方拟合优度检验 + 保底机制验证 |
| 稳定性治理 | Token 失效自动重登、用例数据隔离、并发执行 |
| 缺陷发现能力 | 用例真实抓出 keep-alive 请求体残留 bug 并固化为回归测试 |

---

## 2. 快速开始（5 分钟）

```powershell
# 1. 建虚拟环境并装依赖（版本已锁定）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 跑全部用例（会自动拉起被测服务，随机空闲端口，用完即关）
.venv\Scripts\python.exe -m pytest

# 3. 查看报告与日志
#    reports/report.html  —— HTML 报告
#    logs/api-test-*.log  —— 每次运行的请求日志
```

常用命令：

```powershell
.venv\Scripts\python.exe -m pytest -m smoke              # 只跑冒烟（12 条）
.venv\Scripts\python.exe -m pytest -m negative            # 只跑反例（47 条）
.venv\Scripts\python.exe -m pytest -n 4                   # 并发执行
.venv\Scripts\python.exe -m pytest --alluredir=allure-results   # 输出 Allure 原始结果

# 独立工具
.venv\Scripts\python.exe scripts\smoke_mock_server.py                     # 被测服务契约自检（53 项）
.venv\Scripts\python.exe scripts\verify_gacha_probability.py --draws 10000 # 概率统计检验
.venv\Scripts\python.exe scripts\verify_damage_formula.py                 # 数值批量校验
```

> 对着已有环境跑：设置 `API_TEST_BASE_URL=http://host:port`，框架会跳过本地拉起被测服务。

### CI 门禁设计

`.github/workflows/api-test.yml` 分两层门禁：

| 层 | 内容 | 触发时机 | 理由 |
|---|---|---|---|
| 确定性检查 | SUT 契约自检 53 项 → 136 条回归 `-n 4` → 587 组数值校验 | 每次 push / PR，**阻塞** | 结果确定，红灯必是问题 |
| 统计性检查 | 10000 抽卡方拟合优度检验 | 仅 push 到 main + 每日定时 | 固有误报率 α=0.001，不适合当 PR 硬门禁 |

产物（`reports/report.html`、`logs/`、`allure-results/`）随运行上传，失败时靠它们定位。

> 踩过的坑：cron 写成 `0 19:00 * * *`（6 段）会让整个工作流 `startup_failure`——
> 表现为 **0 个 job、无注解、`name` 回退显示成文件路径**；本地 YAML 能解析但 GitHub 拒绝。
> 正确写法是 5 段 POSIX cron：`0 19 * * *`。
>
> 踩过的坑：GitHub 已弃用 Node 20 的 action 运行时，声明 `runs.using: node20` 的 action
> 会被强制跑在 Node 24 上并产生弃用警告（将来变硬失败）。修复要升到**声明 node24 的版本**：
> `checkout@v5`、`setup-python@v6`、`upload-artifact@v6`。注意 **`upload-artifact@v5` 仍是
> node20**，凭直觉升一版会发现警告还在——判断依据是 action 仓库 `action.yml` 里的
> `runs.using` 字段，而不是版本号大小。

---

## 3. 架构分层

```
api-test-framework/
├── config/config.yaml      环境配置（default 段 + 环境段合并，禁止用例硬编码地址）
├── common/                 框架公共层（与业务领域无关，可直接复用到其它项目）
│   ├── settings.py         配置加载，返回 frozen Settings
│   ├── http_client.py      请求封装：鉴权头、超时、耗时、日志、401 自动重登
│   ├── token_manager.py    Token 缓存 + 失效重登
│   ├── assertions.py       断言封装：失败时打印完整请求与响应
│   ├── data_loader.py      YAML 数据驱动（case_id 注入与去重）
│   ├── logger.py           文件 + 终端双输出日志（UTF-8）
│   └── exceptions.py       按失败领域区分的异常类型
├── mock_server/            被测服务（SUT）：游戏服务端
│   ├── rules.py            数值与概率规则（唯一权威来源，纯函数）
│   ├── store.py            数据与业务规则（违反规则抛 DomainError）
│   └── app.py              HTTP 层：路由 + 鉴权 + 入参校验 + 统一响应
├── testcases/              游戏域业务用例（78 条）
├── tests/                  框架自测（58 条）
│   ├── unit/               纯函数与配置（无网络）
│   ├── integration/        ApiClient / TokenManager / SUT 协议契约
│   └── support/player.py   独立玩家上下文（每用例一个账号）
├── data/                   YAML 数值表与用例数据
├── scripts/                独立验证工具（SUT 自检 / 概率检验 / 数值校验）
└── docs/                   学习与冲刺计划
```

**分层收益**：业务规则在 `store.py`、数值规则在 `rules.py`、协议细节在 `app.py`、
测试框架在 `common/`。测试框架完全不认识游戏概念——领域化改造只动了 SUT 与用例层。

---

## 4. 被测服务（SUT）接口清单

| 方法 | 路径 | 语义 |
|---|---|---|
| GET | `/health` | 健康检查（框架启动探活） |
| POST | `/api/login` | 账号登录（未注册自动注册，签发 Token） |
| POST | `/api/logout` | 登出，服务端立即作废 Token |
| POST | `/api/role/create` | 创角（昵称 ≤ 12 字符） |
| GET | `/api/role` | 角色信息（等级/金币/钻石/体力/保底计数） |
| GET | `/api/bag` | 背包列表（容量、占用、堆叠、绑定） |
| POST | `/api/bag/use` | 使用道具（数量边界，用光释放格子） |
| POST | `/api/gacha/draw` | 抽卡（1 连 / 10 连） |
| POST | `/api/battle/settle` | 战斗结算（伤害公式计算） |
| GET | `/api/mail` | 邮件列表 |
| POST | `/api/mail/claim` | 领取邮件（幂等） |

**状态码约定**（刻意区分，避免"什么都返回 200"的坏味道）：

| 码 | 含义 | 例子 |
|---|---|---|
| 422 | 请求**形状/类型/区间**不合法 | 缺字段、类型错、`times=0` |
| 400 | **业务规则**拒绝 | 钻石不足、道具不足、`times=11` |
| 401 | 未鉴权或 Token 失效 | 无 Bearer 头、Token 过期 |
| 404 | 资源不存在 | 未创角查角色、领不存在的邮件 |
| 409 | 状态冲突 | 重复创角、重复领取邮件 |

---

## 5. 公示规则（数值与概率）

**伤害公式**（权威定义见 `mock_server/rules.py`，README 与代码必须一致）：

```
伤害 = floor( max( atk * skill_ratio - defense * (1 - penetration), 1 )
              * (crit ? crit_multiplier : 1)
              * (1 + damage_bonus) )
```

- 穿透只作用于防御；暴击与增伤是**乘区**，不是加区
- 伤害下限 1（任何情况下不低于 1 点）
- **只在最后一步向下取整**，中间结果不取整（否则误差被放大）
- 已知浮点误差：`200 * 1.15 = 229.99999999999997` → floor 后是 **229** 而非 230。
  该偏差已被用例显式锁定（`damage_float_precision_gap`），而不是假装不存在

**抽卡规则**：

| 项 | 值 |
|---|---|
| 公示概率 | SSR 1.6% / SR 13% / R 85.4% |
| 保底 | 90 抽内必出 SSR（计数在出 SSR 后归零） |
| 消耗 | 单抽 160 钻石，十连 1600 钻石 |
| 新号初始 | 等级 1、金币 1000、钻石 16000、体力 120 |

**可测性设计**（面试常问"随机怎么测"）：

1. 抽卡与暴击支持传入 `seed`，同一 seed 结果完全一致 → 失败用例可复跑
2. 战斗结算支持直接指定 `crit` → 公式验证不依赖概率
3. 保底阈值与抽卡消耗可用环境变量覆盖（`GACHA_PITY_LIMIT` / `GACHA_COST_PER_DRAW`）
   → 概率检验能构造"关闭保底、零消耗"的独立样本，避免保底抬高 SSR 比例

---

## 6. 用例分层与规模

| 目录 | 数量 | 职责 |
|---|---|---|
| `testcases/` | 78 | 登录创角 18、战斗数值 23、抽卡 14、背包 12、邮件 11 |
| `tests/unit/` | 43 | 数值规则 14、断言 9、数据加载 9、配置 7、日志 4 |
| `tests/integration/` | 15 | ApiClient 8、TokenManager 5、SUT 协议契约 2 |
| 标记 | 冒烟 12 / 反例 47 | `-m smoke` / `-m negative` |

**用例隔离策略**：每个用例创建**独立账号 + 已创角**。抽卡会扣钻石、领邮件会改金币、
用道具会改背包——共用账号的用例一旦顺序变化结果就变；独立账号换来的是
**可任意顺序、可并发执行**。

---

## 7. 四个可以拿去面试讲的点

### 7.1 Token 失效自动重登（稳定性治理）
长回归跑到一半 Token 过期，如果没有自愈机制，会产生**几十条假失败**，
排查成本极高。`ApiClient` 收到 401 会清空本地 Token、重登、**只重试一次**
（避免死循环）。有专门用例证明：服务端把 Token 作废后业务请求仍然成功
（`test_should_relogin_and_retry_once_when_token_invalidated`）。

### 7.2 用例抓到的真实缺陷：keep-alive 连接被残留请求体污染
**现象**：先发一个鉴权失败的 POST，同一连接上的下一个请求返回
`501 Unsupported method ('{}POST')`。
**根因**：HTTP/1.1 keep-alive 下，服务端在鉴权阶段提前返回 401 时没有把请求体
从 socket 读走，残留的 `{}` 被下一次请求解析当成请求起始行。
**处理**：修复 + 固化为回归测试（`tests/integration/test_mock_sut_contract.py`，
先复现 RED 再修 GREEN）。
**价值**：这类缺陷**单条用例永远测不出来**，只在"同一连接连续发请求"时出现——
连接池复用、长连接、断线重连场景必须单独设计用例。

### 7.3 抽卡概率大样本统计检验
"概率对不对"不能靠抽几次看看。脚本启动**关闭保底、零消耗**的专用服务实例，
抽 10000 次，用**卡方拟合优度检验**（自由度 2，α=0.001，临界值 13.8155）判断
实际分布与公示概率是否一致，并输出各稀有度 95% 置信区间。

最近一次结果：卡方统计量 9.54 < 13.82 → 无显著差异，概率配置通过。
**为什么必须关掉保底**：保底会系统性抬高 SSR 实际比例，不隔离就得出错误结论。

### 7.4 伤害公式批量校验（数值测试）
脚本**独立实现**一遍公式（刻意不复用被测代码，否则"实现错、验证也错"永远查不出来），
对 11 条人工数值表 + 576 组边界网格（0/1/常规/极大值 × 穿透 × 暴击 × 增伤）逐条比对
服务端返回值。最近一次：587 组全部一致。
**边界覆盖**：攻防为 0、伤害下限、穿透极值 0%/100%、极大攻击力、
浮点误差导致的 ±1 点偏差、向下取整与四舍五入的差异。

---

## 8. 设计取舍（应对追问）

| 追问 | 回答要点 |
|---|---|
| 为什么每个用例独立账号？ | 游戏数据强耦合（抽卡扣费、邮件改金币），共享账号会产生顺序依赖；独立账号换取可并发、可乱序执行 |
| 为什么随机要留 seed 后门？ | 不可复现的失败等于没发现；seed 让失败用例可精确复跑，也让概率检验能构造受控样本 |
| 为什么 422 和 400 要分开？ | 422 是请求形状错误（调错接口/漏传字段），400 是业务规则拒绝（钻石不足）；分开能让失败一眼归因到前端还是策划 |
| 为什么不用 Allure 做主报告？ | Allure 需要额外 CLI 才能看，pytest-html 零门槛；Allure 作为可选项保留（`--alluredir`） |
| 为什么不用 Selenium/Airtest？ | 本项目的目标是服务端接口与数值，UI 自动化投入产出比低，属另一条线（客户端专项） |
| 框架能不能换领域？ | 能。领域化改造只动了 `mock_server/` 与 `testcases/`，`common/` 一行没改 |

---

## 9. 已知限制与后续计划

- 未覆盖：客户端 UI 自动化、长连接协议（WebSocket/Protobuf）、弱网与断线重连、
  性能压测（这些属于游戏测试的专项方向，计划独立开展）
- 概率检验依赖专用服务实例（关闭保底），与业务回归实例配置不同
- 被测服务是内存存储，进程重启即清空；未覆盖数据库断言与测试数据持久化清理

---

## 10. 目录速查

| 想知道什么 | 看哪里 |
|---|---|
| 需求与验收标准 | `tasks/spec.md` |
| 当前进度 | `tasks/todo.md` |
| 踩过的坑与经验 | `tasks/lessons.md` |
| 项目约定（给协作者/未来会话） | `AGENTS.md` |
| 学习路线 | `docs/8周冲刺计划.md` |
