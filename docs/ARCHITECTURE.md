# ARCHITECTURE.md

## 1. 文档目标

本文档定义工业算法插件平台的第一版总体架构，明确平台边界、核心模块、控制面与数据面的职责划分、运行链路、技术栈建议、部署方式与后续演进方向。

本平台的目标不是为某一套固定工艺流程硬编码业务逻辑，而是提供一套可扩展、可审计、可部署、可回滚的通用底座，使得算法功能、模型能力和控制逻辑能够以“插件包”的形式增量接入，而不必频繁修改平台核心代码。

---

## 2. 平台定位

平台定位为：

**面向工业场景的通用算法接入与运行平台**。

平台负责：

- 插件包接入与版本管理
- 数据源接入与统一抽象
- 数据流绑定与输入输出映射
- 插件运行、调度、隔离与生命周期管理
- 结果写回、日志采集、监控告警与审计
- 前端可视化配置与运行状态展示
- 多环境（开发 / 测试 / 生产）下的发布、审批与回滚

平台不直接负责：

- 固定业务算法逻辑的硬编码实现
- 单一厂区单一设备的长期定制耦合
- 将所有控制逻辑固化在 API 服务主进程中
- 允许任意上传代码默认可信运行
- 绕过平台审计链路直接写回现场系统

---

## 3. 总体设计原则

### 3.1 平台本体与插件逻辑解耦

平台提供运行能力，插件提供业务能力。

### 3.2 配置优先于改代码

多数新增能力应优先通过插件包上传、数据流绑定、任务配置实现，而非修改平台核心代码。

### 3.3 运行隔离优先于直接嵌入

上传的插件不应直接运行在主 API 进程中，而应通过独立 Runner 进程或容器运行。

### 3.4 可审计优先于“方便执行”

任何上传、启用、停用、升级、回滚、写回都必须有清晰的审计记录。

### 3.5 版本化优先于覆盖式部署

平台、插件、配置、数据流绑定都应可版本化，并支持回滚。

### 3.6 控制面与数据面分离

平台至少应明确分为：

- **控制面（Control Plane）**：负责元数据、配置、权限、调度定义、审计和可视化管理。
- **数据面（Data Plane）**：负责数据拉取、插件执行、结果校验、写回与运行期状态汇报。

控制面优先保证一致性、可追踪与可管理；数据面优先保证隔离性、稳定性、吞吐与故障恢复。

### 3.7 显式状态优先于隐式约定

插件包、版本、实例、任务、运行记录、写回行为、审批状态都应具有明确状态机和状态迁移规则，避免“文件存在即表示已部署”“目录里有包即表示已启用”这类隐式约定。

### 3.8 最小权限优先于默认放行

插件默认不应具备网络访问、广域文件访问和写回权限。所有高风险能力必须显式声明并经过平台绑定与审批。

### 3.9 兼容演进优先于一次性完备

第一版允许采用轻量实现（如 APScheduler、本地 Runner、Redis/Mock Source），但必须保留后续演进到容器运行时、消息队列和边缘部署的接口边界。

---

## 4. 总体架构分层

平台建议采用以下分层：

### 4.1 展示与配置层（Frontend Console）

负责：

- 登录与权限控制
- 插件包上传
- 插件版本查看与启停
- 数据源管理
- 数据流绑定配置
- 运行实例监控
- 日志、事件、审计记录查看
- 可视化页面配置
- 审批与回滚操作入口

建议技术：

- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- ECharts

### 4.2 平台 API 层（Control Plane API）

负责：

- 用户认证与 RBAC
- 插件包元数据管理
- 数据源配置管理
- 任务调度配置管理
- Runner 生命周期控制
- 日志、审计、事件查询
- 前端控制台 API 提供
- 发布、审批和回滚管理

建议技术：

- Python + FastAPI
- SQLAlchemy
- Pydantic
- PostgreSQL / SQLite（开发阶段）

### 4.3 调度与编排层（Orchestrator）

负责：

- 创建运行实例
- 启动、停止、重启插件
- 定时任务调度
- 健康检查
- 自动重试
- 超时处理
- 崩溃恢复
- 并发控制
- 幂等触发控制

建议实现：

- 平台内部任务编排服务
- APScheduler 作为第一版轻量调度器
- 后续可演进到 Celery / Temporal / Kubernetes Job 等

### 4.4 运行层（Runner Layer）

负责：

- 在独立运行环境中加载插件
- 拉取输入数据
- 执行插件入口
- 采集输出结果
- 执行结果回写前校验
- 上传运行日志、状态和指标
- 响应停止信号与清理临时环境

Runner 类型建议：

- Python Runner
- Binary Runner
- Archive Runner（本质上是对 zip/tar.gz 解压后转交给 Python/Binary Runner）
- 后续预留 Container Runner

### 4.5 数据接入层（Connector Layer）

负责：

- Redis
- TDengine
- HTTP API
- 文件目录
- MQTT
- OPC UA（后续）
- 其他工业协议适配

要求：

- 提供统一读写接口
- 提供标签映射和数据转换能力
- 支持只读与可写权限分离
- 支持质量码、时间戳、单位和异常值语义
- 支持 Mock Source / Mock Sink 以便本地开发与集成测试

### 4.6 数据流与绑定层（Dataflow Binding Layer）

负责：

- 将插件声明的输入输出接口与真实数据源、标签组、查询模板进行绑定
- 定义时间窗、采样粒度、缺失值策略、单位换算和有效范围
- 定义输出限幅、阈值保护、审批确认和写回目标

说明：

- 插件只声明输入输出“语义接口”
- 平台配置真实现场点位、查询方式和回写策略
- 插件不应硬编码厂区标签名

### 4.7 存储层（Metadata & State Storage）

负责保存：

- 用户与权限
- 插件包信息
- 版本记录
- 运行实例信息
- 数据源配置
- 数据流绑定关系
- 审计日志
- 系统事件
- 执行记录
- 审批流记录

建议：

- PostgreSQL：平台元数据
- Redis：状态缓存与短时队列
- 对接外部时序库：现场历史数据

---

## 5. 核心模块设计

### 5.1 Package Registry

负责插件包上传、校验、存储、解压、版本登记和启用状态管理。

### 5.2 Manifest Parser

负责解析插件包中的 `manifest.yaml`，提取运行类型、入口、依赖、资源需求、输入输出定义和权限声明。

### 5.3 Dataflow Manager

负责将插件声明的输入输出字段与真实数据源标签进行绑定，并维护输入窗口、查询方式和输出写回策略。

### 5.4 Runner Manager

负责为插件实例分配运行环境，启动进程，采集退出码、日志、状态和资源占用。

### 5.5 Scheduler Manager

负责周期执行、事件触发、手动执行与计划任务管理。

### 5.6 Writeback Guard

负责控制输出结果是否允许写回、允许写哪些标签、是否经过阈值保护、是否需要人工确认、是否允许部分写回。

### 5.7 Audit Service

负责记录上传、部署、执行、启停、配置修改、写回行为、审批动作和回滚行为。

### 5.8 Observability Service

负责日志、健康状态、事件流、指标统计和告警。

### 5.9 Secret & Credential Broker

负责：

- 按环境安全下发运行期凭证
- 向 Runner 提供最小权限访问票据
- 隔离插件与平台数据库主凭证
- 管理数据源访问密钥的轮换与撤销

### 5.10 Approval & Release Manager

负责：

- 插件版本发布
- 配置变更审批
- 写回能力审批
- 环境间推广（开发 -> 测试 -> 生产）
- 回滚与冻结

### 5.11 State Machine Manager

负责统一维护：

- 插件包状态
- 插件版本状态
- 实例状态
- 单次运行状态
- 发布状态
- 审批状态

---

## 6. 关键状态模型

### 6.1 插件包状态

建议：

- `uploaded`
- `validated`
- `rejected`
- `ready`
- `disabled`
- `archived`

### 6.2 插件版本状态

建议：

- `draft`
- `approved`
- `released`
- `deprecated`
- `revoked`

### 6.3 实例状态

建议：

- `created`
- `configured`
- `enabled`
- `paused`
- `disabled`
- `deleted`

### 6.4 单次运行状态

建议：

- `queued`
- `starting`
- `running`
- `succeeded`
- `failed`
- `timed_out`
- `canceled`
- `writeback_blocked`
- `partially_applied`

说明：

- `partially_applied` 用于输出成功但部分写回被保护规则或审批规则阻断的场景
- `writeback_blocked` 用于插件产生结果但平台禁止直接写回的场景

---

## 7. 典型运行链路

### 7.1 插件上传链路

1. 用户上传插件包
2. 平台保存原始文件
3. 校验包格式与目录结构
4. 解析 `manifest.yaml`
5. 登记插件元数据和版本
6. 进入“待配置”状态

### 7.2 插件配置链路

1. 用户选择插件版本
2. 配置输入数据源与标签绑定
3. 配置输出标签与写回策略
4. 配置运行方式（周期、事件、手动、服务）
5. 配置资源限制与运行参数
6. 保存配置并生成实例模板

### 7.3 插件执行链路

1. 调度器触发任务
2. Runner 启动插件实例
3. Runner 从 Connector 拉取输入
4. Runner 调用插件入口
5. Runner 收集输出与状态
6. 平台执行输出校验与写回控制
7. 写回数据并记录审计日志
8. 前端展示实例状态与日志

### 7.4 写回链路

1. 插件返回标准输出
2. 平台校验字段、类型、范围、单位与目标标签映射
3. Writeback Guard 评估审批、阈值、限幅和环境策略
4. 若允许写回，则通过 Connector 执行
5. 记录写回请求、目标标签、原始值、校正值、执行结果、操作者/触发器
6. 若禁止写回，则保留结果并标记阻断原因

### 7.5 失败与恢复链路

1. Runner 启动失败或插件崩溃
2. 平台记录退出码、stderr、资源占用和超时原因
3. 根据任务策略决定重试、熔断、暂停实例或发出告警
4. 失败不会自动跳过审计记录
5. 高风险失败（持续崩溃 / 连续异常写回）可自动冻结实例

---

## 8. 数据流绑定模型

### 8.1 输入绑定对象

输入绑定至少应支持：

- 单标签读取
- 标签组读取
- 时间窗读取
- 查询模板读取
- 表达式拼装（后续）
- Mock 输入

### 8.2 输入绑定关键属性

建议包含：

- `bindingName`
- `connectorId`
- `queryType`
- `sourceTags`
- `window`
- `sampleInterval`
- `fillPolicy`
- `qualityPolicy`
- `unit`
- `transformRef`
- `timezone`

### 8.3 输出绑定关键属性

建议包含：

- `bindingName`
- `connectorId`
- `targetTag`
- `writable`
- `limitLow`
- `limitHigh`
- `scale`
- `approvalRequired`
- `dryRunAllowed`
- `fallbackPolicy`

### 8.4 缺失值与质量码

第一版至少定义：

- 缺失值如何补齐（丢弃 / 前值填充 / 固定值 / 插值）
- 质量码是否作为输入一部分传给插件
- 低质量数据是否禁止写回

---

## 9. 安全与信任模型

### 9.1 角色建议

建议至少区分：

- 平台管理员
- 开发者 / 插件作者
- 审批人
- 运维人员
- 观察者

### 9.2 高风险动作

以下动作应视为高风险：

- 启用新插件版本
- 修改写回配置
- 放开写回权限
- 提升插件资源上限
- 生产环境部署
- 直接执行生产环境手动作业

### 9.3 信任边界

必须明确：

- 插件包不可信
- Runner 仅在最小权限下信任执行器
- Connector 仅对平台授予受限数据权限
- 现场写回必须经过平台而非插件直连
- 平台数据库凭证不得暴露给插件

### 9.4 第一版安全基线

- 插件默认运行在独立进程中
- 限制工作目录访问范围
- 限制默认网络访问能力
- 限制可写目标标签范围
- 限制 CPU、内存、超时时间
- 记录标准输出、标准错误与退出码
- 禁止插件直接接触平台数据库连接信息

### 9.5 后续增强项

- 容器沙箱
- seccomp / namespace 隔离
- 包签名校验
- 白名单依赖源
- 租户级命名空间隔离
- 双人审批与变更冻结窗口

---

## 10. 技术选型建议

### 10.1 平台层

- Frontend: Vue 3 + TypeScript + Vite
- Backend API: FastAPI
- ORM: SQLAlchemy
- DB: PostgreSQL
- Cache/State: Redis
- Scheduler: APScheduler

### 10.2 插件运行层

- Python Runner: Python 3.12+
- Binary Runner: Rust / C++ / Go 编译产物均可接入
- Archive Support: zip / tar.gz

### 10.3 性能核心

对以下高性能部分，可使用 Rust 实现：

- 数据流解析与转换
- 高吞吐缓存处理
- 安全校验工具
- 本地 Runner 守护进程
- 二进制插件 SDK
- 资源限制与进程监督工具

平台与 Rust 模块可通过以下方式集成：

- CLI 调用
- HTTP/gRPC
- 本地 socket
- Python FFI / pyo3（仅在必要时）

### 10.4 何时不必使用 Rust

以下部分原则上不优先 Rust 化：

- 普通 CRUD 接口
- 权限管理后台
- 通用配置查询
- 低吞吐调度配置管理
- 文档型后台逻辑

---

## 11. 仓库建议结构

```text
platform/
├─ frontend/                     # 前端控制台
├─ apps/
│  ├─ api/                       # FastAPI 控制平面
│  ├─ runner/                    # 通用 Runner 管理服务
│  └─ worker/                    # 任务执行与调度
├─ crates/
│  ├─ core-runtime/              # Rust 运行时核心
│  ├─ connector-utils/           # Rust 数据处理工具
│  ├─ supervisor/                # Rust 进程监督与资源限制工具
│  └─ binary-sdk/                # 二进制插件 SDK
├─ plugin_sdk/
│  ├─ python/                    # Python 插件 SDK
│  ├─ binary/                    # Binary 插件约定与示例
│  └─ examples/                  # 示例插件
├─ packages/
│  ├─ manifests/                 # Manifest schema 与模板
│  └─ shared-types/              # 共享类型定义
├─ docs/
│  ├─ ARCHITECTURE.md
│  ├─ PLUGIN_SPEC.md
│  ├─ AGENTS.md
│  ├─ RUNNER_PROTOCOL.md
│  └─ DATAFLOW_SPEC.md
└─ scripts/
```

---

## 12. 元数据模型建议（最小集合）

建议至少显式建模以下对象：

- `users`
- `roles`
- `permissions`
- `plugin_packages`
- `plugin_versions`
- `plugin_instances`
- `data_sources`
- `input_bindings`
- `output_bindings`
- `schedules`
- `runs`
- `run_logs`
- `writeback_records`
- `audit_events`
- `approval_requests`
- `environments`
- `sites` / `namespaces`

说明：

- 即使第一版不做完整多租户，也建议预留 `environment` 与 `namespace` 的外键位点
- 不建议把“厂区 / 产线 / 设备”直接写死在表结构里作为唯一层级，宜保留可演进空间

---

## 13. 部署模式建议

### 13.1 本地开发模式

- SQLite / PostgreSQL（二选一）
- Redis
- Mock Source / Mock Sink
- 本地 Runner
- 单机文件存储

### 13.2 单节点试点模式

- PostgreSQL
- Redis
- 本地或边缘主机 Runner
- 文件或对象存储保存插件包
- 单环境审批链

### 13.3 生产模式（后续）

- PostgreSQL 主从或托管服务
- Redis 高可用
- 多 Runner 节点
- 统一日志与指标系统
- 审批、回滚、冻结窗口
- 容器隔离或边缘节点代理

---

## 14. 第一阶段最小可用目标（MVP）

第一版不追求全协议支持，优先完成：

- Python 插件包上传
- `manifest.yaml` 解析
- 本地 zip 插件解压
- 数据源配置：Redis / Mock Source
- 输出写回：Redis / Mock Sink
- Runner 进程执行
- 日志查看
- 周期任务执行
- 插件启停
- 基础 RBAC
- Dry-run 模式写回校验
- 基础审计日志

---

## 15. 后续演进方向

### Phase 1

平台骨架 + Python Runner + 插件包规范

### Phase 2

zip/tar.gz 包、版本管理、审批、审计、日志增强

### Phase 3

Binary Runner、Rust 核心模块、更多连接器

### Phase 4

容器化沙箱、多租户、灰度发布、双人审批流、边缘部署

---

## 16. 非目标说明

第一版暂不包含：

- 全自动 AI 生成插件并直接上线
- 任意上传代码默认可信执行
- 完整工业协议全覆盖
- 跨厂区多租户调度系统
- 完整云原生集群编排

---

## 17. 结语

本架构的核心目标，是将现有“固定业务系统”演进为“通用插件平台”。

后续具体设计应优先围绕以下几项推进：

1. 插件包规范稳定化
2. Runner 生命周期标准化
3. 数据流绑定配置化
4. 写回权限与审批模型收敛
5. 元数据模型稳定化
