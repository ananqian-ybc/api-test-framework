# 经验记录（本项目特定：模式、坑、对后续工作重要的上下文）

## 2026-10-09 会话

### 1. 用例抓到的真实 bug：keep-alive 连接被残留请求体污染
- **现象**：先发一个鉴权失败的 POST（服务端在 `_require_auth()` 阶段直接 401），
  同一 keep-alive 连接上的下一个请求返回 `501 Unsupported method ('{}POST')`。
- **根因**：HTTP/1.1 keep-alive 下，服务端提前返回时没有把请求体从 socket 读走，
  残留的 `{}` 被下一次请求解析当成请求起始行。
- **修复**：`mock_server/app.py` 增加 `_drain_request_body()`，在 `_send_json` /
  `_send_empty` 中统一排空未读请求体；`handle_one_request()` 每条请求重置标记
  （注意 `BaseHTTPRequestHandler` 一个实例会服务同一连接上的多个请求，标记不能只放在 `__init__`）。
- **回归测试**：`tests/integration/test_mock_sut_contract.py`（先复现 RED 再修）。
- **教训**：**单条用例永远测不出这类问题** —— 它只在"同一连接连续发请求"时出现。
  连接池复用、长连接、断线重连场景必须单独设计用例。

### 2. 超时 ≠ 连不上：异常映射必须区分语义
- `requests.ConnectTimeout` 是 `ConnectionError` 与 `Timeout` 的**共同子类**，
  捕获顺序写错就会把"服务没启动"报成"请求超时"。
- 正确映射：`ConnectTimeout` / `ConnectionError` → `ApiConnectionError`（连不上），
  `ReadTimeout` / `Timeout` → `ApiTimeoutError`（响应超时）。
- Windows 上连 127.0.0.1 的关闭端口可能表现为**超时**而非拒绝连接，
  所以"服务未启动"的用例要断言**可读错误信息**，不要断言异常类型来自哪个底层库。

### 3. 目标岗位修正：通用测试 → **游戏测试**
- 使用者目标是游戏测试岗，被测系统与用例必须领域化（登录创角 / 背包 / 抽卡 / 战斗结算），
  框架核心层（配置、HTTP 封装、鉴权、断言、数据驱动）**无需改动，可完整复用**。
- 游戏测试的特有考点需单独补：弱网与断线重连、协议（长连接/Protobuf）、
  数值验证（公式边界/溢出/浮点）、概率验证（大样本统计检验）、兼容性、
  性能（FPS/内存/发热）、安全（改包/内存修改）。

### 4. 工具链坑
- `pytest 9` 没有 `--no-html` 参数（不要凭印象写参数，报错会直接终止收集）。
- PowerShell 控制台默认 GBK：跑 Python 前设 `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`，
  否则中文输出乱码（文件本身是 UTF-8，不影响）。
