# TODO：api-test-framework 实施计划

> 规则：完成一项勾一项，**绝不最后批量勾选**。每条里程碑都要能自主验证。

## M0 准备 【完成】
- [x] 环境确认：Python 3.11.4 / Java 21 / git 2.49
- [x] 写规格 `tasks/spec.md`（含 v2 游戏域修正）
- [x] 写 8 周冲刺计划 `docs/8周冲刺计划.md`
- [x] 规格确认：stdlib mock SUT / pytest-html 为主 + Allure 可选 / 依赖装项目内 .venv

## M1 被测服务（SUT）【完成】
- [x] v1：任务 CRUD mock（已被 v2 替代）
- [x] v2：**游戏服务端 mock** —— 登录/登出/创角/角色/背包/道具/抽卡/战斗结算/邮件列表/领邮件（11 接口）
- [x] 分层：`rules.py`（数值与概率权威来源）/ `store.py`（游戏规则）/ `app.py`（HTTP 层）
- [x] `scripts/smoke_mock_server.py`：53 项契约自检全 PASS（可重复执行）
- [x] 验收 AC2' 通过

## M2 框架公共层（TDD 先红后绿）【完成】
- [x] 先写失败测试（RED：29 failed + 12 errors，均为 NotImplementedError / 断言失败）
- [x] `common/logger.py`、`settings.py`、`http_client.py`、`token_manager.py`、`data_loader.py`、`assertions.py`
- [x] **用例抓到真实 bug**：keep-alive 残留请求体导致后续请求 501 → 修复 + 回归测试
- [x] 验收 AC3、AC5 通过
- [x] 领域化验证：`common/` 一行未改即可切换领域（仅 TokenManager 登录路径参数化）

## M3 游戏域用例与数据表 【完成】
- [x] `tests/support/player.py`：每用例独立账号 + 已创角（消除顺序依赖）
- [x] `testcases/`：登录创角 18、战斗数值 23、抽卡 14、背包 12、邮件 11 = **78 条**
- [x] `data/`：数值表与反例表 5 个（伤害 11 条、战斗反例 7 条、抽卡反例 7 条、登录 5 条、创角 5 条）
- [x] 验收 AC4' 通过（≥40 条游戏域用例）

## M4 报告、并发与 CI 【完成】
- [x] pytest-html 默认报告 + Allure 可选（`--alluredir`）
- [x] `-n 4` 并发通过（AC6）
- [x] 验收 AC1、AC7 通过
- [ ] `.github/workflows/api-test.yml`（AC8，仓库托管到 GitHub 时补）

## M5 独立验证工具与文档 【完成】
- [x] `scripts/verify_gacha_probability.py`：10000 抽卡方检验（关闭保底的专用实例）→ AC10
- [x] `scripts/verify_damage_formula.py`：独立公式 + 587 组数值比对 → AC11
- [x] `README.md`（含公示规则、设计取舍、面试话术）
- [x] `AGENTS.md`（分层红线与完成定义）
- [x] `requirements.txt`（版本锁定）
- [x] git init + 分层提交历史
- [x] 验收 AC9 通过

## 复盘
- **规模**：136 条用例（游戏域 78 + 框架自测 58）｜冒烟 12｜反例 47
- **性能**：全量回归 5.1s；`-n 4` 并发 4.8s
- **抓到的真实缺陷**：SUT keep-alive 残留请求体污染（已修复 + 回归固化）
- **可量化的简历数据**：11 个接口｜136 条用例｜10000 抽概率检验｜587 组数值校验｜并发 4 进程
- **踩坑记录**：见 `tasks/lessons.md`
- **下一步（按价值排序）**：
  1. 接入 GitHub Actions（AC8）并把 `-n 4` 作为 CI 默认
  2. Allure CLI 落地并附报告截图（简历附件用）
  3. 增加弱网/重连专项：延迟注入 + 连接复用 + 幂等重放
  4. 抽卡概率检验纳入定时任务（每日跑一次，防配置被误改）
