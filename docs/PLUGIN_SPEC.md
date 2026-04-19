# PLUGIN_SPEC.md

## 1. 文档目标

本文档定义平台第一版插件包规范。目标是让 Python 脚本、二进制程序、压缩包都能以统一的方式被平台识别、安装、配置和运行。

插件包是平台扩展能力的基本单元。

---

## 2. 设计原则

### 2.1 统一抽象

无论插件使用 Python、Rust、C++ 还是其他语言，平台都将其识别为“插件包 + Manifest + 入口程序”的统一结构。

### 2.2 包格式与运行方式分离

zip 或 tar.gz 只是分发形式，不是运行协议。平台解压后仍需按 Manifest 识别真正的运行类型。

### 2.3 声明式优先

插件包必须通过 `manifest.yaml` 明确声明其输入输出、运行类型、资源需求和权限要求。

### 2.4 最小权限

插件默认不具备写回权限，必须显式声明并经过平台配置绑定。

### 2.5 平台负责写回

插件只产生结果，不直接负责现场写回。写回由平台按绑定配置、审批规则和保护策略执行。

### 2.6 运行协议优先于语言细节

第一版应优先稳定“Runner 与插件之间的输入输出协议”，而不是为每种语言过早做复杂 SDK。

---

## 3. 支持的插件类型

### 3.1 Python 插件

适用于：

- 推理脚本
- 数据处理脚本
- 周期分析任务
- 轻量服务型逻辑

### 3.2 Binary 插件

适用于：

- Rust / C / C++ / Go 编译产物
- MATLAB 编译产物
- 高性能计算模块

### 3.3 Archive 插件

适用于：

- 以 zip / tar.gz 打包的 Python 或 Binary 插件
- 包含模型文件、配置文件、依赖资源的完整插件分发包

### 3.4 Service 插件（运行语义）

说明：

- `service` 是运行方式，不是分发格式
- Python/Binary 插件都可以声明自己是服务型插件
- 服务型插件需要额外的心跳、就绪状态和停止协议

---

## 4. 插件包目录约定

### 4.1 通用目录结构

```text
my_plugin/
├─ manifest.yaml
├─ README.md
├─ assets/
├─ config/
├─ logs/
└─ runtime/
```

其中：

- `manifest.yaml`：必需
- `README.md`：建议
- `assets/`：模型、静态资源、权重文件
- `config/`：插件内部默认配置
- `logs/`：运行日志输出目录（可选）
- `runtime/`：真正的运行文件目录（建议）

### 4.2 Python 插件示例

```text
temp_predictor/
├─ manifest.yaml
├─ requirements.txt
├─ runtime/
│  ├─ main.py
│  └─ plugin.py
├─ assets/
│  └─ model.pkl
└─ README.md
```

### 4.3 Binary 插件示例

```text
control_optimizer/
├─ manifest.yaml
├─ runtime/
│  ├─ bin/
│  │  └─ optimizer
│  └─ lib/
├─ assets/
│  └─ rules.json
└─ README.md
```

---

## 5. Manifest 规范

### 5.1 基本字段

`manifest.yaml` 为必需文件，第一版建议包含以下字段：

```yaml
apiVersion: plugin.platform/v1
kind: PluginPackage
metadata:
  name: rotary-kiln-optimizer
  displayName: Rotary Kiln Optimizer
  version: 0.1.0
  author: Your Name
  description: Minimal optimizer plugin for industrial control.
  tags:
    - optimization
    - kiln
spec:
  pluginType: python
  packageFormat: directory
  entry:
    mode: function
    file: runtime/main.py
    callable: run
  runtime:
    pythonVersion: "3.11"
    workingDir: "."
    timeoutSec: 30
    memoryMB: 512
    cpuLimit: 1
  schedule:
    type: interval
    intervalSec: 30
  inputs:
    - name: state_history
      type: timeseries
      required: true
      window: 5
  outputs:
    - name: action_recommendation
      type: object
      writable: true
  permissions:
    network: false
    filesystem: scoped
    writeback: false
compatibility:
  platformApi: ">=0.1.0"
  runnerApi: ">=0.1.0"
```

---

## 6. Manifest 字段说明

### 6.1 metadata

- `name`: 插件唯一标识，建议使用 kebab-case
- `displayName`: 展示名称
- `version`: 版本号，使用 semver
- `author`: 作者或团队
- `description`: 简介
- `tags`: 分类标签

### 6.2 spec.pluginType

允许值：

- `python`
- `binary`
- `archive`

说明：

- `archive` 仅表示分发形式；解压后仍需声明内部实际运行方式
- 第一版可允许 `archive` 与 `entry.resolvedType` 组合使用

### 6.3 spec.entry

描述插件入口。

#### Python 插件

```yaml
entry:
  mode: function
  file: runtime/main.py
  callable: run
```

或：

```yaml
entry:
  mode: cli
  command: ["python", "runtime/main.py"]
```

#### Binary 插件

```yaml
entry:
  mode: cli
  command: ["./runtime/bin/optimizer"]
```

#### Service 插件

```yaml
entry:
  mode: service
  command: ["python", "runtime/service.py"]
  healthEndpoint: "/health"
  readySignal: "stdout:READY"
```

### 6.4 spec.runtime

描述运行约束：

- Python 版本
- 工作目录
- 超时
- CPU 限制
- 内存限制
- 环境变量
- 操作系统 / 架构要求

示例：

```yaml
runtime:
  os: linux
  arch: x86_64
  timeoutSec: 60
  memoryMB: 1024
  cpuLimit: 2
  env:
    LOG_LEVEL: INFO
```

### 6.5 spec.schedule

描述默认执行方式：

- `manual`
- `interval`
- `cron`
- `event`
- `service`

示例：

```yaml
schedule:
  type: interval
  intervalSec: 30
```

### 6.6 spec.inputs

描述插件声明的输入接口，不直接绑定真实标签。

字段建议：

- `name`
- `type`
- `required`
- `window`
- `schema`
- `description`
- `unit`
- `qualityAware`

### 6.7 spec.outputs

描述插件输出接口。

字段建议：

- `name`
- `type`
- `writable`
- `description`
- `unit`
- `limits`
- `approvalHint`

### 6.8 spec.permissions

建议字段：

- `network`
- `filesystem`
- `writeback`
- `subprocess`

### 6.9 compatibility

用于约束插件包与平台/Runner 的兼容范围。

建议字段：

- `platformApi`
- `runnerApi`
- `supportedEnvironments`

### 6.10 configSchema（建议）

如插件希望暴露可配置参数，可声明：

```yaml
configSchema:
  type: object
  properties:
    safe_mode:
      type: boolean
      default: true
    horizon:
      type: integer
      minimum: 1
      maximum: 300
```

---

## 7. 输入输出协议

### 7.1 第一版推荐标准

平台对插件入口传递标准 JSON 结构，避免不同语言 SDK 差异过大。

输入示例：

```json
{
  "context": {
    "run_id": "run-20260418-0001",
    "plugin": "rotary-kiln-optimizer",
    "version": "0.1.0",
    "instance_id": "inst-001",
    "environment": "dev",
    "timestamp": "2026-04-18T10:00:00Z",
    "trigger": {
      "type": "interval",
      "schedule_id": "sch-001"
    }
  },
  "inputs": {
    "state_history": [[1100, 4.5, 1050], [1105, 4.3, 1055]],
    "action_history": [[300, 35, 600, 700, 280, 5, 0.40]]
  },
  "config": {
    "window": 5,
    "safe_mode": true
  }
}
```

输出示例：

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
  }
}
```

### 7.2 输出状态约定

建议允许以下状态：

- `success`
- `partial_success`
- `failed`

说明：

- `partial_success` 表示插件产生了部分有效输出，但不是所有声明输出都成功
- 最终是否允许部分写回，由平台控制

### 7.3 平台保留字段

输出中以下字段应视为平台保留字段：

- `status`
- `outputs`
- `logs`
- `metrics`
- `error`

插件不应在 `outputs` 内重复定义这些关键字。

---

## 8. Runner 与插件的交互约定

### 8.1 第一版交互方式

建议支持两种最小方式：

1. `stdin -> stdout`
2. `input.json -> output.json`

### 8.2 CLI 模式约定

对于 CLI 模式：

- Runner 可将输入写入 stdin
- 插件输出标准 JSON 到 stdout
- 非 JSON 内容应输出到 stderr 或日志文件
- 非零退出码表示运行失败

### 8.3 文件模式约定

如果使用文件模式，建议 Runner 约定：

- 输入文件：`./.platform/input.json`
- 输出文件：`./.platform/output.json`
- 元数据文件：`./.platform/context.json`

### 8.4 服务模式约定

服务型插件需支持：

- 启动就绪判定
- 健康检查
- 停止信号处理
- 心跳或就绪状态上报

第一版允许用以下任一方式：

- stdout 输出固定 `READY`
- 本地 HTTP 健康检查端点
- 本地 socket 就绪信号

---

## 9. Python 插件入口规范

第一版推荐函数式入口：

```python
from typing import Dict, Any


def run(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "outputs": {},
        "logs": [],
        "metrics": {}
    }
```

要求：

- 返回标准字典
- 不直接操作平台数据库
- 不直接写回现场标签
- 写回由平台执行
- 不依赖未声明的环境变量
- 对非法输入显式返回错误或抛出异常

---

## 10. Binary 插件入口规范

Binary 插件建议采用 CLI 模式。

Runner 行为：

1. 将标准 JSON 输入写入临时文件或标准输入
2. 执行二进制入口命令
3. 读取标准输出或指定结果文件
4. 解析为标准 JSON 输出

建议兼容：

- stdin -> stdout
- input.json -> output.json

对 Binary 插件，建议额外声明：

```yaml
runtime:
  os: linux
  arch: x86_64
entry:
  mode: cli
  command: ["./runtime/bin/optimizer"]
```

---

## 11. 压缩包规范

支持格式：

- `.zip`
- `.tar.gz`

要求：

- 根目录下必须包含 `manifest.yaml`
- 不允许路径穿越
- 不允许软链接逃逸
- 解压后总大小可配置限制
- 可执行文件需显式声明
- 包内容数量和单文件大小应受限
- 平台应记录 SHA256 或等效校验值

---

## 12. 数据流绑定说明

### 12.1 插件声明与现场绑定分离

插件在 Manifest 中只声明输入输出接口：

```yaml
inputs:
  - name: kiln_state
    type: timeseries
    required: true
outputs:
  - name: recommended_action
    type: object
    writable: true
```

真正的现场绑定应由平台配置完成，而不是由插件包硬编码。

### 12.2 第一版绑定规则建议

平台绑定层至少应支持：

- 单字段到单标签
- 多字段到标签组
- 时间窗读取
- 输出对象字段映射到多个目标标签
- 输出前限幅与审批标记

---

## 13. 输出校验与写回策略

### 13.1 平台校验职责

平台在写回前至少应校验：

- 字段是否存在
- 类型是否匹配
- 单位是否兼容
- 范围是否超限
- 是否允许该实例写回此目标
- 是否需要审批

### 13.2 部分成功处理

当插件返回 `partial_success` 或输出部分字段缺失时，平台可选择：

- 全部阻断
- 仅保留结果不写回
- 对通过校验的字段部分写回

该策略应由实例配置明确，而不应由插件自行决定。

### 13.3 Dry-run 模式

平台应支持 dry-run：

- 执行插件
- 验证输出
- 不真正写回
- 保留审计记录与对比结果

---

## 14. 版本与兼容性要求

### 14.1 版本号

插件版本采用 semver：

- `MAJOR.MINOR.PATCH`

### 14.2 平台兼容性

Manifest 中可声明：

```yaml
compatibility:
  platformApi: ">=0.1.0"
  runnerApi: ">=0.1.0"
```

### 14.3 版本升级原则

建议：

- Manifest 结构不兼容变更时提升 `apiVersion`
- 插件自身行为变更按 semver 管理
- 平台应拒绝明显不兼容的包进入生产发布流程

---

## 15. 校验规则

平台上传时应校验：

- `manifest.yaml` 是否存在
- `name`、`version` 是否有效
- 入口文件是否存在
- 声明类型是否受支持
- 资源限制是否超出平台阈值
- 包内文件大小与数量是否合理
- 二进制目标平台是否匹配
- `configSchema` 是否可解析
- 声明的输出是否包含非法保留字段

---

## 16. 安全限制

第一版建议默认策略：

- 默认不允许网络访问
- 默认不允许写回
- 默认不允许访问插件目录外文件
- 默认限制执行时间与内存
- 默认记录 stdout/stderr
- 默认不允许直接访问平台数据库
- 默认不允许安装未受控来源依赖

---

## 17. 示例：最小 Python 插件

```yaml
apiVersion: plugin.platform/v1
kind: PluginPackage
metadata:
  name: demo-python-plugin
  displayName: Demo Python Plugin
  version: 0.1.0
  author: Dev
  description: Demo plugin
spec:
  pluginType: python
  packageFormat: zip
  entry:
    mode: function
    file: runtime/main.py
    callable: run
  runtime:
    pythonVersion: "3.11"
    timeoutSec: 20
    memoryMB: 256
  schedule:
    type: manual
  inputs:
    - name: value
      type: number
      required: true
  outputs:
    - name: doubled
      type: number
      writable: false
  permissions:
    network: false
    filesystem: scoped
    writeback: false
compatibility:
  platformApi: ">=0.1.0"
  runnerApi: ">=0.1.0"
```

---

## 18. 结语

平台后续的 Python SDK、Binary SDK 与上传流程，都应以本规范为基础推进。

后续若实现与规范冲突，以平台 schema 定义与 Runner 协议实现为准，并同步更新本文档。

建议下一个紧邻文档为：

- `RUNNER_PROTOCOL.md`
- `DATAFLOW_SPEC.md`
