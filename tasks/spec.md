# 规格：pytest 接口自动化测试框架（api-test-framework）

- Date: 2026-02-XX（会话当日）
- Status: Proposed（待确认）
- Deciders: 使用者（应届生，Java + Python）

## Goal（一句话）

搭建一套**分层、可离线跑通、可接入 CI** 的接口自动化测试框架，作为求职简历的核心项目；
框架自带一个可复现的被测系统（stdlib mock 服务），任何人 clone 后一条命令即可跑出报告。

**为什么是这个：** 应届测试岗面试官必追五点 —— 分层设计、稳定性治理、数据管理、断言与定位、
CI 集成。框架必须真实覆盖这五点，而不是只有一堆 `requests.get` 脚本。

## Inputs / Outputs

| 方向 | 内容 |
|---|---|
| Inputs | `config/config.yaml`（环境/base_url/超时）、`data/*.yaml`（测试数据）、被测服务 |
| Outputs | pytest 退出码（0=全绿，作为 CI 质量门禁） |
| | `reports/report.html`（pytest-html，零门槛可看） |
| | `reports/allure-results/`（Allure 原始结果，可选生成 HTML） |
| | `logs/run-<timestamp>.log`（结构化运行日志） |

## 关键设计（面试要讲的就是这几条）

1. **分层**：`config` / `common` / `api` / `testcases` / `data` / `mock_server` / `reports`
2. **鉴权治理**：token 单例缓存 + 失效自动重登，避免每条用例重复登录（性能与稳定性双收益）
3. **数据驱动**：yaml 数据 + `pytest.mark.parametrize`，数据与代码分离
4. **断言封装**：`assert_that` 统一断言，失败时打印请求/响应全文，缩短定位时间
5. **环境隔离**：`--env` 参数切换 dev/ci，配置集中在 config 层
6. **被测系统自持**：stdlib `http.server` 实现 mock 后端（鉴权 / CRUD / 分页 / 错误码），
   保证**离线可跑、CI 可跑、面试可现场演示**

## Constraints（不可让步）

- Python 3.11；依赖锁定版本；依赖装在项目内 `.venv`
- **不依赖外网**，不依赖 Docker 才能跑起来
- 单文件 ≤ 400 行、函数 ≤ 40 行、嵌套 ≤ 3 层（框架自身也要守规范）
- 框架自身代码（`common/` 层）必须有单元测试，且**测试先于实现**

## Edge Cases（必须覆盖）

- 未带 token / token 非法 / token 过期 → 401，框架自动重登一次后用例仍应通过
- 资源不存在 → 404；参数缺失或非法 → 422
- 分页越界、`size` 超过上限
- 并发执行（`-n 4`）时登录态不与用例状态互相污染
- 被测服务未启动 → 明确报错（含"请先启动 mock_server"），而不是 30 秒超时堆栈

## Out of Scope（本版本明确不做）

- UI 自动化（Playwright / Selenium）—— 后续独立仓库
- 性能压测（JMeter / Locust）—— 第 7 周单独做
- 数据库断言（被测系统为内存存储）
- 契约测试（Pact）、动态 Mock 桩
- 测试数据的分布式清理方案

## Acceptance Criteria（可勾选的完成定义）

- [ ] AC1 `python -m pytest` 一条命令全绿，且**不依赖外网**
- [ ] AC2 mock_server 覆盖 7 个接口与 5 类状态码（200/201/204/401/404/422）
- [ ] AC3 `common/` 四个模块各有单元测试，且先红后绿
- [ ] AC4 用例总数 ≥ 40，正例与反例齐备
- [ ] AC5 token 失效自动重登**可被测试证明**（注入坏 token → 用例仍通过）
- [ ] AC6 `-n 4` 并发执行通过
- [ ] AC7 产出 HTML 报告与运行日志
- [ ] AC8 CI 配置（GitHub Actions）跑同一命令
- [ ] AC9 README 让陌生人 5 分钟跑起来

## Test Stubs（先写这些测试，再写实现）

- `test_http_client.py::should_attach_auth_header_when_token_present`
- `test_http_client.py::should_raise_clear_error_when_service_unreachable`
- `test_http_client.py::should_log_request_and_response_on_assertion_failure`
- `test_token_manager.py::should_cache_token_and_login_only_once`
- `test_token_manager.py::should_relogin_and_retry_once_when_token_expired`
- `test_data_loader.py::should_load_yaml_and_parametrize_cases`
- `test_data_loader.py::should_raise_clear_error_when_yaml_missing`
- `test_assertions.py::should_include_full_response_in_failure_message`

---

# v2 领域化修正（目标岗位：游戏测试）

## 变更原因

使用者应聘的是**游戏测试岗**。框架核心层（配置 / HTTP 封装 / 鉴权 / 断言 / 数据驱动）
与领域无关，**不需要改动**；需要领域化的是被测系统与用例层。

## 变更内容

### 被测系统改为「游戏服务端」mock

| 接口 | 语义 | 覆盖的游戏测试考点 |
|---|---|---|
| `POST /api/login` | 账号登录（未注册自动注册） | 鉴权、Token、异常账号 |
| `POST /api/logout` | 登出使 Token 失效 | 断线/重连、失效重登 |
| `POST /api/role/create` | 创角 | 唯一性、重复创角 409 |
| `GET /api/role` | 角色信息 | 初始值与数值一致性 |
| `GET /api/bag` | 背包列表 | 容量与占用一致性 |
| `POST /api/bag/use` | 使用道具 | 数量边界、用光移除格子 |
| `POST /api/gacha/draw` | 抽卡（1/10 连） | **概率、保底、扣费、随机可复现** |
| `POST /api/battle/settle` | 战斗结算 | **伤害公式、取整、边界、溢出** |
| `POST /api/mail/claim` | 领取邮件 | **重复领取幂等**、越权隔离 |

### 可测性设计（重要，面试可讲）

1. **随机可复现**：抽卡与暴击支持传入 `seed`，同一 seed 结果完全一致 —— 随机系统
   不给后门就没法做回归，这是游戏测试的真实工程取舍。
2. **公式可精确验算**：战斗结算支持直接指定 `crit`，无需依赖概率即可验证公式。
3. **数据隔离**：每个账号独立角色/背包/邮件/保底计数，用例可用独立账号做到互不污染。

### 数值权威来源

伤害公式与概率表**只定义在 `mock_server/rules.py`**，README 同步公示；
`scripts/verify_damage_formula.py` 必须**独立实现**同一公式（不复用 rules.py），
否则"验证"与"实现"同源，等于没验证。

```
伤害 = floor( max( atk * skill_ratio - defense * (1 - penetration), 1 )
              * (crit ? crit_multiplier : 1)
              * (1 + damage_bonus) )
```
- 取整：只在最后一步向下取整（floor），中间结果不取整
- 伤害下限：1（任何情况下不低于 1）
- 抽卡公示概率：SSR 1.6% / SR 13% / R 85.4%；**90 抽保底必出 SSR**
- 单抽消耗 160 钻石；十连 1600 钻石

### 更新的验收标准

- [x] AC2' 游戏服务端 mock 覆盖 10 个接口与 200/201/400/401/404/409/422 状态码
- [ ] AC4' 游戏域用例 ≥ 40 条，覆盖概率、保底、数值边界、幂等、越权隔离
- [ ] AC10 抽卡概率统计检验脚本（大样本 + 置信区间 + 保底单独验证）
- [ ] AC11 伤害公式批量验证脚本（独立实现 + 数值表驱动）

## v2 反目标（明确不做）

- 不做游戏客户端 / Unity 工程（UI 自动化在 W7 用 Airtest 单独练）
- 不做帧同步与服务端广播（协议层只到 HTTP JSON，长连接专项另行练习）
- 不做真实的渠道支付链路（充值只用邮件/钻石模拟）

