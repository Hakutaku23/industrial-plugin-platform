# RUNNER_PROTOCOL.md

## 1. 文档目标

本文档定义工业算法插件平台第一版 **Runner 执行协议**。

目标是明确以下边界：

- 控制面（Control Plane）如何向 Runner 下发一次运行任务
- Runner 如何准备运行环境、拉取输入、执行插件、收集输出并上报结果
- 插件与 Runner 之间的标准输入输出契约
- 运行状态机、错误分类、重试边界、停止语义和日志要求
- 写回前校验、部分成功处理和审计要求

本协议优先服务于以下目标：

- **跨语言一致性**：Python / Binary / Archive 插件都遵循统一执行契约
- **隔离执行**：插件不在 API 主进程中运行
- **可恢复**：失败、超时、中断和崩溃都可被识别与处理
- **可审计**：每一次执行都有明确记录、输入版本、输出状态与写回结果
- **可演进**：第一版可运行于本地进程模型，后续可迁移到容器或边缘节点

---

## 2. 术语定义

### 2.1 Control Plane

平台控制面，负责：

- 任务定义
- 运行实例创建
- 调度触发
- 元数据管理
- 审批与回滚
- 审计记录

### 2.2 Data Plane

平台数据面，负责：

- 数据拉取
- 插件执行
- 输出校验
- 写回控制
- 运行时状态汇报

### 2.3 Runner

Runner 是数据面执行单元，负责在隔离环境中运行插件。

Runner 本身不负责：

- 用户权限决策
- 平台元数据直接修改
- 审批结果伪造
- 绕过写回保护直接落现场系统

### 2.4 Plugin Instance

插件实例是“某个插件版本 + 某套绑定配置 + 某个运行方式”的部署对象。

### 2.5 Run

一次 Run 表示某个插件实例在某次触发条件下的一次具体执行。

每次 Run 必须有唯一 `run_id`。

### 2.6 Writeback Guard

写回保护模块，负责：

- 输出字段是否允许写回
- 是否命中阈值保护
- 是否需要人工确认
- 是否允许部分写回

---

## 3. 协议边界

本协议覆盖以下链路：

1. 控制面创建运行任务
2. Runner 接收任务并进入准备阶段
3. Runner 拉取输入并构造标准执行载荷
4. Runner 调用插件入口
5. Runner 解析插件输出
6. Runner 执行输出校验与写回前检查
7. Runner 执行写回或阻断写回
8. Runner 回传状态、日志、指标和错误信息

本协议不覆盖：

- 控制面审批流具体实现
- 前端 UI 展示细节
- 连接器内部驱动细节
- 容器编排平台的调度实现细节

---

## 4. Runner 架构职责

Runner 必须实现以下职责：

### 4.1 环境准备

- 解包插件（如需要）
- 校验入口文件
- 创建临时运行目录
- 注入运行时配置与环境变量
- 准备输入载荷文件或标准输入流

### 4.2 执行控制

- 启动子进程或语言运行时
- 跟踪 PID / 进程组
- 实施超时限制
- 实施 CPU / 内存 / 目录边界限制
- 支持停止与强制终止

### 4.3 输出处理

- 读取标准输出、标准错误与结果文件
- 解析标准输出 JSON 或输出文件 JSON
- 记录插件日志与 Runner 日志
- 执行输出 schema 校验

### 4.4 数据面收口

- 将插件输出提交给写回保护模块
- 执行写回前限幅与策略检查
- 记录写回结果
- 回传运行状态与指标

### 4.5 审计与上报

- 上报 `run_id`、实例版本、触发方式、开始/结束时间
- 上报最终状态
- 上报退出码、错误类别、关键日志、指标

---

## 5. Runner 类型

第一版协议支持以下 Runner 语义：

### 5.1 Python Runner

适用于：

- 函数式 Python 插件
- CLI 方式 Python 插件

### 5.2 Binary Runner

适用于：

- Rust / C / C++ / Go 编译产物
- 其他平台可执行二进制

### 5.3 Archive Runner

用于处理 `.zip` / `.tar.gz` 分发包。

说明：

- Archive Runner 不直接定义执行语义
- 它负责安全解压并解析 Manifest
- 解压后转交 Python Runner 或 Binary Runner

### 5.4 Service Runner

用于运行 `schedule.type=service` 的长驻插件。

额外职责：

- 就绪探测
- 心跳监控
- 平滑停止
- 异常退出重启策略

---

## 6. 运行状态机

每个 Run 必须有显式状态。

### 6.1 标准状态

- `CREATED`：控制面已创建 Run，尚未分配给 Runner
- `QUEUED`：已进入调度队列，等待执行
- `ASSIGNED`：已分配给某个 Runner
- `PREPARING`：Runner 正在准备运行环境
- `INPUT_READY`：输入数据与执行载荷已准备完成
- `STARTING`：插件进程正在启动
- `RUNNING`：插件正在执行
- `OUTPUT_PENDING`：插件进程已结束，Runner 正在解析输出
- `VALIDATING`：正在校验输出与写回策略
- `WRITEBACK_PENDING`：符合写回条件，等待执行写回
- `COMPLETED`：执行完成，且未发生错误
- `PARTIAL_SUCCESS`：插件执行成功，但部分输出或部分写回失败
- `FAILED`：执行失败
- `TIMED_OUT`：执行超时
- `CANCELLED`：运行前被取消
- `STOPPING`：收到停止指令，正在终止
- `STOPPED`：已停止
- `CRASHED`：Runner 或插件异常崩溃，未正常收尾

### 6.2 合法迁移

推荐迁移路径：

```text
CREATED -> QUEUED -> ASSIGNED -> PREPARING -> INPUT_READY -> STARTING -> RUNNING
RUNNING -> OUTPUT_PENDING -> VALIDATING -> WRITEBACK_PENDING -> COMPLETED
```

异常路径示例：

```text
RUNNING -> TIMED_OUT
RUNNING -> FAILED
RUNNING -> STOPPING -> STOPPED
STARTING -> CRASHED
VALIDATING -> PARTIAL_SUCCESS
WRITEBACK_PENDING -> PARTIAL_SUCCESS
```

### 6.3 状态机要求

- 不允许从终态直接回到运行态
- `COMPLETED`、`FAILED`、`TIMED_OUT`、`STOPPED`、`CANCELLED`、`CRASHED` 为终态
- `PARTIAL_SUCCESS` 视为终态，但必须带明确原因与影响范围
- 每次状态迁移必须记录时间戳与可选原因码

---

## 7. Run 对象最小模型

每次 Run 至少包含以下字段：

```json
{
  "run_id": "run-20260418-000001",
  "instance_id": "inst-001",
  "plugin_name": "rotary-kiln-optimizer",
  "plugin_version": "0.1.0",
  "trigger_type": "schedule",
  "trigger_ref": "schedule-30s",
  "runner_type": "python",
  "status": "QUEUED",
  "attempt": 1,
  "max_attempts": 3,
  "created_at": "2026-04-18T10:00:00Z"
}
```

建议扩展字段：

- `environment`
- `site_id`
- `line_id`
- `binding_version`
- `manifest_digest`
- `package_digest`
- `approval_snapshot_id`
- `requested_by`
- `assigned_runner_id`

---

## 8. 控制面到 Runner 的任务载荷

控制面下发给 Runner 的任务对象应与插件输入区分开来。

### 8.1 Runner Task 示例

```json
{
  "task": {
    "run_id": "run-20260418-000001",
    "instance_id": "inst-001",
    "attempt": 1,
    "trigger_type": "schedule",
    "trigger_ref": "interval:30s"
  },
  "plugin": {
    "name": "rotary-kiln-optimizer",
    "version": "0.1.0",
    "plugin_type": "python",
    "package_format": "zip",
    "package_path": "/data/packages/rotary-kiln-optimizer/0.1.0.zip",
    "manifest": {}
  },
  "instance": {
    "binding_version": "bind-v3",
    "runtime_overrides": {
      "timeoutSec": 20,
      "env": {
        "LOG_LEVEL": "INFO"
      }
    }
  },
  "input_binding": {
    "resolved_inputs": []
  },
  "output_binding": {
    "resolved_outputs": []
  },
  "policies": {
    "writeback_enabled": false,
    "allow_partial_writeback": false,
    "require_approval_for_writeback": true
  }
}
```

### 8.2 任务下发要求

- Runner 接收到任务后必须校验 `run_id` 唯一性与必要字段完整性
- Runner 不应信任插件包内部任何可覆盖控制面决策的字段
- `runtime_overrides` 优先级高于 Manifest 默认值
- 未通过审批的高风险写回任务不得进入实际写回阶段

---

## 9. Runner 到插件的执行载荷

Runner 传给插件的内容称为 **Execution Payload**。

第一版推荐统一 JSON 结构。

### 9.1 标准输入载荷

```json
{
  "context": {
    "run_id": "run-20260418-000001",
    "instance_id": "inst-001",
    "plugin": "rotary-kiln-optimizer",
    "version": "0.1.0",
    "timestamp": "2026-04-18T10:00:00Z",
    "attempt": 1,
    "trigger_type": "schedule",
    "environment": "dev"
  },
  "inputs": {
    "state_history": {
      "type": "timeseries",
      "values": [[1100, 4.5, 1050], [1105, 4.3, 1055]],
      "timestamps": ["2026-04-18T09:59:30Z", "2026-04-18T10:00:00Z"],
      "quality": ["good", "good"],
      "unit": null
    }
  },
  "config": {
    "safe_mode": true,
    "window": 5
  },
  "capabilities": {
    "network": false,
    "filesystem": "scoped",
    "writeback": false
  }
}
```

### 9.2 输入载荷要求

- `context` 必须包含可审计标识
- `inputs` 仅包含已绑定并已拉取成功的输入语义接口
- 插件不应自行推断真实现场标签名
- `config` 可包含实例级参数覆盖
- `capabilities` 只用于告知插件当前权限，不代表插件可绕过 Runner 直接执行敏感操作

---

## 10. 插件执行模式

### 10.1 Function 模式

适用于 Python 插件。

Runner 行为：

1. 加载指定模块文件
2. 调用声明的 callable，例如 `run(payload)`
3. 接收返回值并转为标准输出结果

要求：

- 返回结构必须符合标准输出协议
- 插件不应在该模式下长期阻塞

### 10.2 CLI 模式

适用于 Python / Binary 插件。

Runner 行为：

- 可将输入通过以下方式之一传递：
  - 标准输入 `stdin`
  - `input.json` 文件
- 可从以下方式之一获取输出：
  - 标准输出 `stdout`
  - `output.json` 文件

建议优先顺序：

1. stdout JSON
2. output.json

### 10.3 Service 模式

适用于长驻进程。

Runner 行为：

- 启动服务进程
- 等待就绪信号
- 持续健康检查
- 通过定义的本地接口投递任务或请求
- 在停止时发送优雅关闭信号

第一版建议：

- `service` 仅用于明确需要常驻的插件
- 非必要不要将普通周期任务实现为服务型插件

---

## 11. 插件标准输出协议

插件执行完成后，必须返回标准 JSON 结果。

### 11.1 标准输出结构

```json
{
  "status": "success",
  "outputs": {
    "action_recommendation": {
      "rl_004": 300,
      "rl_005": 35
    },
    "reward": 2.31
  },
  "logs": [
    "prediction completed"
  ],
  "metrics": {
    "latency_ms": 15
  },
  "artifacts": [],
  "warnings": []
}
```

### 11.2 `status` 允许值

- `success`
- `partial_success`
- `failed`

说明：

- 插件侧 `partial_success` 仅表示插件内部逻辑部分完成
- 平台最终 Run 状态仍由 Runner 和平台综合判定

### 11.3 输出要求

- `outputs` 字段只允许声明在 Manifest 中的输出键
- 不允许额外注入未声明写回对象
- `logs` 应为简短执行日志，不应替代标准错误流
- `metrics` 应为结构化数值指标
- `artifacts` 可声明额外产物路径或引用，但第一版可仅预留

---

## 12. 输出解析与校验

Runner 在解析插件输出后，必须执行以下校验：

### 12.1 基础校验

- 是否为有效 JSON
- 是否包含 `status`
- `outputs` 是否为对象
- 字段类型是否与 Manifest 对齐

### 12.2 语义校验

- 输出名是否在 `spec.outputs` 中声明
- 不允许未声明的写回输出进入写回流程
- 对于数值型输出，可执行范围校验、NaN/Inf 检查
- 对于对象型输出，可执行 schema 校验

### 12.3 校验结果分类

- `VALID`：通过全部校验
- `VALID_WITH_WARNINGS`：通过，但存在非阻断警告
- `INVALID_OUTPUT`：输出结构或类型非法
- `UNSAFE_OUTPUT`：触发安全规则，不允许继续写回

---

## 13. 部分成功语义

平台必须显式支持 `PARTIAL_SUCCESS`，避免将所有非完美执行一律归为失败。

### 13.1 可归为部分成功的场景

- 插件成功返回结果，但某个非关键输出字段缺失
- 关键输出通过，但某些非写回指标未生成
- 写回目标中部分标签成功、部分被保护规则拦截
- 日志 / 指标上报失败，但主结果有效

### 13.2 不应归为部分成功的场景

- 插件主输出完全不可解析
- 关键写回值类型错误或危险
- 进程崩溃且无可信结果
- 超时且未生成可信输出

### 13.3 记录要求

`PARTIAL_SUCCESS` 必须记录：

- 成功部分
- 失败部分
- 是否已执行任何写回
- 是否触发人工介入

---

## 14. 写回协议

插件输出本身不等于写回结果。

写回必须由平台执行，且走独立阶段。

### 14.1 写回前流程

1. 输出解析完成
2. 按输出绑定找到真实目标
3. 执行字段级校验
4. 执行阈值保护 / 限幅 / 单位转换
5. 检查当前环境是否允许写回
6. 检查是否需要审批确认
7. 执行写回
8. 记录审计结果

### 14.2 写回结果结构

建议保存如下结构：

```json
{
  "writeback": {
    "status": "partial_success",
    "targets": [
      {
        "output": "action_recommendation.rl_004",
        "target": "redis:sthb:DCS_AO_RTO_012_AI",
        "status": "success"
      },
      {
        "output": "action_recommendation.rl_005",
        "target": "redis:sthb:DCS_AO_RTO_013_AI",
        "status": "blocked",
        "reason": "approval_required"
      }
    ]
  }
}
```

### 14.3 写回阻断条件

出现以下任一条件时，必须阻断对应写回：

- 输出未声明为可写
- 当前环境为只读环境
- 未通过审批
- 命中限幅保护或危险阈值
- 目标连接器处于不可写状态
- 输出校验失败

---

## 15. 错误分类

Runner 应将错误分为可操作类别，而不是统一写成“执行失败”。

### 15.1 推荐错误码

- `E_TASK_INVALID`：任务对象非法
- `E_PACKAGE_INVALID`：插件包非法
- `E_MANIFEST_INVALID`：Manifest 不合法
- `E_ENTRY_NOT_FOUND`：入口不存在
- `E_INPUT_RESOLUTION_FAILED`：输入绑定解析失败
- `E_INPUT_FETCH_FAILED`：输入数据拉取失败
- `E_START_FAILED`：进程启动失败
- `E_RUNTIME_CRASHED`：进程崩溃
- `E_TIMEOUT`：执行超时
- `E_OUTPUT_PARSE_FAILED`：输出无法解析
- `E_OUTPUT_INVALID`：输出校验失败
- `E_WRITEBACK_BLOCKED`：写回被策略阻断
- `E_WRITEBACK_FAILED`：写回执行失败
- `E_STOP_REQUESTED`：收到停止指令
- `E_RUNNER_INTERNAL`：Runner 内部错误

### 15.2 错误记录要求

至少记录：

- 错误码
- 错误阶段
- 简短消息
- 详细堆栈或 stderr 摘要
- 是否可重试

---

## 16. 重试与幂等

### 16.1 重试原则

不是所有失败都可重试。

可重试场景示例：

- 临时性输入拉取失败
- Runner 节点瞬时异常
- 连接器瞬时不可用

不建议自动重试场景：

- Manifest 非法
- 输出 schema 非法
- 明确命中写回危险规则

### 16.2 幂等要求

- 每次 Run 都必须有唯一 `run_id`
- 重试时 `run_id` 可保持不变，但 `attempt` 必须递增
- 写回前必须检查是否已执行过同一 `run_id + output target + attempt` 的写回
- 默认不允许因为 Runner 崩溃导致同一结果被重复写回两次

---

## 17. 停止与取消协议

### 17.1 Cancel

适用于尚未实际启动插件进程的 Run。

- `CREATED` / `QUEUED` / `ASSIGNED` 阶段可进入 `CANCELLED`

### 17.2 Stop

适用于已启动的 Run。

Runner 处理：

1. 状态改为 `STOPPING`
2. 发送优雅终止信号
3. 等待宽限期
4. 超过宽限期则强制终止
5. 记录最终状态 `STOPPED` 或 `CRASHED`

### 17.3 停止要求

- 停止动作必须记录是谁发起、何时发起、原因是什么
- 若已完成写回，不得因停止而回溯篡改已发生审计记录

---

## 18. 日志协议

### 18.1 日志来源

每次 Run 至少采集三类日志：

- Runner 结构化日志
- 插件 stdout
- 插件 stderr

### 18.2 日志最小字段

```json
{
  "timestamp": "2026-04-18T10:00:01Z",
  "run_id": "run-20260418-000001",
  "source": "runner",
  "level": "INFO",
  "message": "plugin process started"
}
```

### 18.3 日志要求

- Runner 日志建议结构化
- 插件 stdout/stderr 可原样保存，但建议做大小限制
- 超大日志需截断并记录截断标记
- 日志与审计记录必须能通过 `run_id` 关联

---

## 19. 指标协议

Runner 每次 Run 至少记录以下指标：

- `queue_delay_ms`
- `prepare_latency_ms`
- `input_fetch_latency_ms`
- `execution_latency_ms`
- `output_parse_latency_ms`
- `writeback_latency_ms`
- `total_latency_ms`
- `peak_memory_mb`（如可得）
- `cpu_time_ms`（如可得）

服务型插件额外建议：

- `uptime_sec`
- `restart_count`
- `heartbeat_gap_ms`

---

## 20. 服务型插件补充协议

### 20.1 就绪判断

第一版支持以下一种或多种方式：

- stdout 出现固定标记，如 `READY`
- 本地 HTTP 健康接口返回 `200 OK`
- 本地 socket 成功握手

### 20.2 心跳

服务型插件应周期性提供心跳。

若超过心跳超时时间：

- 标记为 `UNHEALTHY`
- 可触发重启策略
- 记录事件与审计

### 20.3 任务投递

服务型插件若支持请求式调用，建议通过本地 IPC / HTTP / gRPC 进行。

第一版要求：

- 必须限定为本地受控接口
- 不应暴露为默认公网接口

---

## 21. 目录与临时文件约定

Runner 执行时建议使用如下目录布局：

```text
/workdir/
├─ package/           # 解包后的插件目录
├─ input/
│  └─ input.json
├─ output/
│  └─ output.json
├─ logs/
│  ├─ stdout.log
│  └─ stderr.log
└─ meta/
   └─ run_context.json
```

要求：

- 每次 Run 使用独立工作目录
- 工作目录生命周期应与 Run 绑定
- 可配置是否保留失败现场
- 默认不允许访问工作目录外任意路径

---

## 22. 安全要求

### 22.1 默认限制

- 默认无外网访问
- 默认无平台元数据库访问
- 默认仅允许访问工作目录
- 默认不允许写回
- 默认限制 CPU、内存与时间

### 22.2 包与路径安全

- 解压时必须防止路径穿越
- 不允许软链接逃逸
- 可执行文件必须来自已声明入口
- 不应信任包内自带的启动脚本去覆盖 Runner 规则

### 22.3 机密信息

- Runner 不应将敏感密钥直接写入插件日志
- 平台下发给 Runner 的密钥应最小化、短期化
- 插件默认不应获得控制面数据库连接信息

---

## 23. 审计要求

每次 Run 至少应可追踪：

- 谁触发
- 触发来源（计划 / 手动 / 事件）
- 使用了哪个插件版本
- 使用了哪个绑定版本
- 运行在哪个环境 / Runner 上
- 最终状态
- 是否发生写回
- 写回到哪些目标
- 是否命中保护规则
- 是否经过审批

---

## 24. 第一版最小实现建议

为避免过早复杂化，第一版建议最小实现如下：

1. 支持 `python:function` 与 `binary:cli`
2. 支持 `stdin -> stdout JSON` 与 `input.json -> output.json`
3. 支持本地进程隔离运行
4. 支持 Redis / Mock Source 作为输入
5. 支持 Redis / Mock Sink 作为写回目标
6. 支持基础状态机与错误码
7. 支持超时、停止、日志采集
8. 支持写回前阻断策略
9. 支持部分成功状态

### 24.1 第一版可暂缓项

- 容器沙箱
- 远程 Runner 集群
- 服务型插件复杂调度
- 分布式日志聚合
- 丰富 artifact 存储系统

---

## 25. 与其他文档的关系

本协议应与以下文档保持一致：

- `ARCHITECTURE.md`
- `PLUGIN_SPEC.md`
- `AGENTS.md`

后续如需继续细化，建议新增：

- `DATAFLOW_SPEC.md`
- `SECURITY_MODEL.md`
- `METADATA_MODEL.md`

---

## 26. 结语

Runner 协议是平台从“能上传插件”走向“能稳定执行插件”的关键收口层。

后续开发中，任何影响以下内容的改动，都应优先同步更新本文档：

- 插件执行入口
- 输入输出协议
- 状态机
- 错误码
- 写回前保护策略
- 日志和审计字段

