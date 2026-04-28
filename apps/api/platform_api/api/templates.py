from __future__ import annotations

import io
import textwrap
import zipfile
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from platform_api.security import Principal, require_permission


router = APIRouter(prefix="/api/v1", tags=["templates"])


@dataclass(frozen=True)
class TemplateDefinition:
    name: str
    filename: str
    category: str
    title: str
    description: str
    builder: Callable[[], bytes]


def _dedent(content: str) -> str:
    return textwrap.dedent(content).lstrip("\n")


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _python_function_plugin() -> bytes:
    return _zip({
        "manifest.yaml": _dedent("""
            apiVersion: plugin.platform/v1
            kind: PluginPackage
            metadata:
              name: python-function-template
              displayName: Python Function Template
              version: 0.1.0
              author: local
              description: Basic Python function plugin template.
            spec:
              pluginType: python
              packageFormat: zip
              entry:
                mode: function
                type: file
                file: main.py
                callable: run
              runtime:
                pythonVersion: '3.11'
                timeoutSec: 30
                memoryMB: 512
                workingDir: .
              schedule:
                type: manual
              inputs:
                - name: input
                  type: number
                  required: true
              outputs:
                - name: result
                  type: number
                  required: true
                  writable: true
              permissions:
                network: false
                filesystem: scoped
                writeback: true
                subprocess: false
            compatibility:
              platformApi: '>=0.2.0'
              runnerApi: runner-task/v2
              supportedEnvironments: [dev, factory]
        """),
        "main.py": _dedent("""
            def run(payload):
                value = float(payload.get('inputs', {}).get('input', 0))
                return {'status': 'success', 'outputs': {'result': value}, 'metrics': {}, 'logs': []}
        """),
        "README.md": "# Python 函数插件模板\n\n上传 zip 后绑定输入输出即可运行。\n",
    })


def _model_package() -> bytes:
    return _zip({
        "manifest.yaml": _dedent("""
            schema: ipp-model/v1
            model:
              name: my-model
              version: 20260101-001
              framework: sklearn
              task_type: regression
              entry_artifact: model
              description: Replace placeholder artifacts before upload.
            model_family:
              family_fingerprint: mf_replace_with_your_model_family
            runtime_contract:
              managed_by_plugin: true
            artifacts:
              model:
                path: artifacts/model.placeholder
                type: user_defined_model
              x_scaler:
                path: artifacts/x_scaler.placeholder
                type: user_defined_scaler
            metrics:
              note: put model metrics in metrics.json
        """),
        "checksums.json": "{\n  \"schema\": \"ipp-model-checksums/v1\",\n  \"files\": {}\n}\n",
        "metrics.json": "{\n  \"schema\": \"ipp-model-metrics/v1\",\n  \"metrics\": {},\n  \"metrics_completeness\": {\"reported\": false}\n}\n",
        "artifacts/model.placeholder": "replace with model file\n",
        "artifacts/x_scaler.placeholder": "replace with scaler file\n",
        "README.md": "# 模型包模板\n\n模型名称、版本、family_fingerprint 和 artifacts 均由 manifest.yaml 声明。\n",
    })


def _redis_model_plugin() -> bytes:
    return _zip({
        "manifest.yaml": _dedent("""
            apiVersion: plugin.platform/v2
            kind: PluginPackage
            metadata:
              name: redis-model-inference-template
              displayName: Redis Model Inference Template
              version: 0.1.0
              author: local
              description: Redis inputs + context.model artifacts inference template.
            modelDependency:
              required: true
              familyFingerprint: mf_replace_with_your_model_family
              requiredArtifacts: [model, x_scaler]
            spec:
              pluginType: python
              packageFormat: zip
              entry:
                mode: function
                type: file
                file: main.py
                callable: run
              runtime:
                pythonVersion: '3.11'
                timeoutSec: 60
                memoryMB: 2048
                workingDir: .
              schedule:
                type: manual
              inputs:
                - name: input_014
                  type: number
                  required: true
                - name: input_015
                  type: number
                  required: true
              outputs:
                - name: predict
                  type: number
                  required: true
                  writable: true
              permissions:
                network: false
                filesystem: scoped
                writeback: true
                subprocess: false
            compatibility:
              platformApi: '>=0.2.0'
              runnerApi: runner-task/v2
              supportedEnvironments: [dev, factory]
        """),
        "main.py": _dedent("""
            def run(payload):
                inputs = payload.get('inputs', {})
                model_ctx = payload.get('context', {}).get('model') or {}
                artifacts = model_ctx.get('artifacts') or {}
                model_path = artifacts.get('model', {}).get('path')
                x_scaler_path = artifacts.get('x_scaler', {}).get('path')
                value = float(inputs.get('input_014', 0)) + float(inputs.get('input_015', 0))
                return {
                    'status': 'success',
                    'outputs': {'predict': value},
                    'metrics': {'model_path': str(model_path), 'x_scaler_path': str(x_scaler_path)},
                    'logs': ['redis model inference template completed'],
                }
        """),
        "requirements.txt": "numpy\nscikit-learn\njoblib\n",
        "README.md": "# Redis + 模型推理插件模板\n\n平台负责 Redis 输入绑定和模型物化，插件只读取 payload.inputs 与 payload.context.model.artifacts。\n",
    })


def _redis_rw_plugin() -> bytes:
    return _zip({
        "manifest.yaml": _dedent("""
            apiVersion: plugin.platform/v1
            kind: PluginPackage
            metadata:
              name: redis-read-write-template
              displayName: Redis Read Write Template
              version: 0.1.0
              author: local
              description: Redis input and writeback template.
            spec:
              pluginType: python
              packageFormat: zip
              entry:
                mode: function
                file: main.py
                callable: run
              runtime:
                timeoutSec: 30
                memoryMB: 512
              schedule:
                type: manual
              inputs:
                - name: input
                  type: number
                  required: true
              outputs:
                - name: output
                  type: number
                  required: true
                  writable: true
              permissions:
                network: false
                filesystem: scoped
                writeback: true
                subprocess: false
            compatibility:
              platformApi: '>=0.2.0'
              runnerApi: runner-task/v2
        """),
        "main.py": "def run(payload):\n    return {'status': 'success', 'outputs': {'output': payload['inputs'].get('input')}, 'metrics': {}, 'logs': []}\n",
    })


def _tdengine_history_plugin() -> bytes:
    """TDengine history template aligned with the field-tested manifest structure."""
    return _zip({
        "manifest.yaml": _dedent("""
            apiVersion: plugin.platform/v1
            kind: PluginPackage
            metadata:
              name: tdengine-two-point-history-template
              displayName: TDengine 双点位历史窗口模板
              version: 0.1.0
              author: PSELAB
              description: 使用 TDengine 历史窗口输入，统计两个点位的均值、末值和差值。
              tags:
                - tdengine
                - history
                - template
            spec:
              pluginType: python
              packageFormat: zip
              entry:
                mode: function
                file: runtime/main.py
                callable: run
              runtime:
                pythonVersion: '3.12'
                timeoutSec: 30
                memoryMB: 256
                workingDir: .
              schedule:
                type: manual
              inputs:
                - name: history_df
                  type: dataframe
                  required: true
                  description: 平台从 TDengine 读取后传入的 dataframe split payload。
                  schema:
                    ippBinding:
                      bindingType: history
                      connectorType: tdengine
                      lockConnectorType: true
                      sourceTags:
                        - DCS_AO_001
                        - DCS_AO_002
                      lockSourceTags: true
                      window:
                        start_offset_min: 60
                        end_offset_min: 0
                        sample_interval_sec: 60
                        lookback_before_start_sec: 600
                        fill_method: ffill_then_interpolate
                        strict_first_value: true
              outputs:
                - name: ao_001_mean
                  type: number
                  required: false
                  description: DCS_AO_001 均值
                - name: ao_002_mean
                  type: number
                  required: false
                  description: DCS_AO_002 均值
                - name: latest_delta
                  type: number
                  required: false
                  description: 最新时刻 DCS_AO_001 - DCS_AO_002
                - name: row_count
                  type: integer
                  required: false
                  description: 输入历史窗口行数
              permissions:
                network: false
                filesystem: none
                writeback: false
                subprocess: false
            compatibility:
              platformApi: '>=0.2.0'
              runnerApi: runner-task/v2
              supportedEnvironments:
                - dev
                - factory
        """),
        "runtime/main.py": _dedent("""
            from __future__ import annotations

            def run(payload):
                inputs = payload.get('inputs') or {}
                history_df = inputs.get('history_df') or inputs.get('history_window') or inputs.get('training_window')
                columns, rows = _extract_split_dataframe(history_df)
                if len(columns) < 2:
                    raise ValueError('TDengine history dataframe requires at least two value columns')
                first_col, second_col = columns[0], columns[1]
                first_values = _numeric_column(rows, 0)
                second_values = _numeric_column(rows, 1)
                if not first_values or not second_values:
                    raise ValueError('TDengine history dataframe contains no numeric values')
                latest_delta = first_values[-1] - second_values[-1]
                return {
                    'status': 'success',
                    'outputs': {
                        'ao_001_mean': sum(first_values) / len(first_values),
                        'ao_002_mean': sum(second_values) / len(second_values),
                        'latest_delta': latest_delta,
                        'row_count': len(rows),
                    },
                    'metrics': {
                        'row_count': len(rows),
                        'columns': columns,
                        'first_column': first_col,
                        'second_column': second_col,
                    },
                    'logs': ['tdengine history template completed'],
                }

            def _extract_split_dataframe(value):
                if not isinstance(value, dict):
                    raise ValueError('history input must be a dataframe split payload')
                columns = [str(item) for item in value.get('columns', [])]
                rows = value.get('data', [])
                if not isinstance(rows, list):
                    raise ValueError('history dataframe data must be a list')
                return columns, rows

            def _numeric_column(rows, index):
                result = []
                for row in rows:
                    try:
                        value = float(row[index])
                    except (TypeError, ValueError, IndexError):
                        continue
                    result.append(value)
                return result
        """),
        "README.md": _dedent("""
            # TDengine 双点位历史窗口模板

            该模板与现场已验证的 `history` 输入绑定结构一致：

            - `schema.ippBinding.bindingType = history`
            - `schema.ippBinding.connectorType = tdengine`
            - `schema.ippBinding.sourceTags` 固化历史点位
            - `schema.ippBinding.window` 固化默认历史窗口

            平台负责从 TDengine 查询历史数据，并将 dataframe split payload 注入 `payload.inputs.history_df`。
            插件不直接连接 TDengine。
        """),
    })


def _tdengine_model_update_trainer_plugin() -> bytes:
    return _zip({
        "manifest.yaml": _dedent("""
            apiVersion: plugin.platform/v2
            kind: PluginPackage
            metadata:
              name: tdengine-model-update-trainer-template
              displayName: TDengine 模型更新训练模板
              version: 0.1.0
              author: local
              description: 通过模型更新任务的数据源绑定读取 TDengine 历史窗口，并输出 candidate_model。
              tags:
                - tdengine
                - model-update
                - trainer
            modelUpdate:
              enabled: true
              role: trainer
              requiredArtifacts:
                - model
                - x_scaler
            spec:
              pluginType: python
              packageFormat: zip
              entry:
                mode: function
                type: file
                file: main.py
                callable: run
              runtime:
                pythonVersion: '3.12'
                timeoutSec: 300
                memoryMB: 2048
                workingDir: .
              schedule:
                type: manual
              inputs:
                - name: training_window
                  type: dataframe
                  required: true
                  description: 平台从 TDengine 读取后传入的训练历史窗口。
                  schema:
                    ippBinding:
                      bindingType: history
                      connectorType: tdengine
                      lockConnectorType: true
                      sourceTags:
                        - DCS_001
                        - DCS_002
                      lockSourceTags: true
                      window:
                        start_offset_min: 10080
                        end_offset_min: 0
                        sample_interval_sec: 60
                        lookback_before_start_sec: 600
                        fill_method: ffill_then_interpolate
                        strict_first_value: true
              outputs:
                - name: update_required
                  type: boolean
                  required: true
                - name: candidate_created
                  type: boolean
                  required: true
                - name: training_metrics
                  type: object
                  required: false
              permissions:
                network: false
                filesystem: scoped
                writeback: false
                subprocess: false
            compatibility:
              platformApi: '>=0.2.0'
              runnerApi: runner-task/v2
              supportedEnvironments: [dev, factory]
        """),
        "main.py": _dedent("""
            from __future__ import annotations

            from pathlib import Path

            def run(payload):
                ctx = payload.get('context', {}).get('model_update') or {}
                candidate_dir = Path(ctx.get('candidate_model_dir') or 'candidate_model')
                window = (payload.get('inputs') or {}).get('training_window')
                columns = window.get('columns', []) if isinstance(window, dict) else []
                rows = window.get('data', []) if isinstance(window, dict) else []
                # 这里保留最小骨架。实际项目应在此调用用户自己的：
                # data preprocessing / feature engineering / model training / evaluation / candidate writer。
                candidate_dir.mkdir(parents=True, exist_ok=True)
                return {
                    'status': 'success',
                    'outputs': {
                        'update_required': False,
                        'candidate_created': False,
                        'training_metrics': {'rows': len(rows), 'columns': columns},
                    },
                    'metrics': {'rows': len(rows), 'columns': columns, 'source': 'payload.inputs.training_window'},
                    'logs': ['tdengine model update trainer template loaded training_window successfully'],
                }
        """),
        "README.md": _dedent("""
            # TDengine 模型更新训练模板

            该模板用于模型更新任务，不用于普通实例回写。

            平台职责：
            - 根据模型更新任务中的输入绑定读取 TDengine 历史数据；
            - 注入 `payload.inputs.training_window`；
            - 注入 `payload.context.model_update.candidate_model_dir`；
            - 训练插件生成 candidate_model 后由平台登记为新模型版本。

            用户职责：
            - 在 `main.py` 中替换训练逻辑；
            - 将候选模型写入 `candidate_model_dir`；
            - 输出 `update_required/candidate_created/training_metrics`。
        """),
    })


def _python_extension_module_plugin() -> bytes:
    return _zip({
        "manifest.yaml": _dedent("""
            apiVersion: plugin.platform/v2
            kind: PluginPackage
            metadata:
              name: python-extension-module-template
              displayName: Python Extension Module Template
              version: 0.1.0
              author: local
              description: CPython extension module plugin template. Build the .so first, then upload the generated package.
            spec:
              pluginType: python
              packageFormat: zip
              entry:
                mode: function
                type: module
                module: native_plugin
                callable: run
              runtime:
                pythonVersion: '3.11'
                timeoutSec: 30
                memoryMB: 512
                workingDir: .
              schedule:
                type: manual
              inputs:
                - name: input
                  type: number
                  required: true
              outputs:
                - name: result
                  type: number
                  required: true
                  writable: true
              permissions:
                network: false
                filesystem: scoped
                writeback: true
                subprocess: false
            compatibility:
              platformApi: '>=0.2.0'
              runnerApi: runner-task/v2
              supportedEnvironments: [factory]
        """),
        "native_plugin.c": _dedent(r'''
            #define PY_SSIZE_T_CLEAN
            #include <Python.h>

            static PyObject* native_run(PyObject* self, PyObject* args) {
                PyObject* payload = NULL;
                if (!PyArg_ParseTuple(args, "O", &payload)) return NULL;
                PyObject* outputs = PyDict_New();
                PyDict_SetItemString(outputs, "result", PyFloat_FromDouble(0.0));
                PyObject* result = PyDict_New();
                PyDict_SetItemString(result, "status", PyUnicode_FromString("success"));
                PyDict_SetItemString(result, "outputs", outputs);
                PyDict_SetItemString(result, "metrics", PyDict_New());
                PyDict_SetItemString(result, "logs", PyList_New(0));
                Py_DECREF(outputs);
                return result;
            }

            static PyMethodDef NativePluginMethods[] = {
                {"run", native_run, METH_VARARGS, "Run plugin with IPP payload."},
                {NULL, NULL, 0, NULL}
            };

            static struct PyModuleDef native_plugin_module = {
                PyModuleDef_HEAD_INIT, "native_plugin", "IPP CPython extension example.", -1, NativePluginMethods
            };

            PyMODINIT_FUNC PyInit_native_plugin(void) { return PyModule_Create(&native_plugin_module); }
        '''),
        "setup.py": "from setuptools import Extension, setup\nsetup(name='ipp-native-plugin-template', version='0.1.0', ext_modules=[Extension('native_plugin', sources=['native_plugin.c'])])\n",
        "README.md": "# Python 扩展模块插件模板\n\n该模板需在目标环境编译后上传。\n",
    })


_TEMPLATES = {
    "python-function-plugin-template.zip": TemplateDefinition("python-function-plugin-template.zip", "python-function-plugin-template.zip", "plugin", "Python 函数插件模板", "最小函数式插件模板。", _python_function_plugin),
    "python-function-package.zip": TemplateDefinition("python-function-package.zip", "python-function-plugin-template.zip", "plugin", "Python 函数插件模板", "旧地址兼容。", _python_function_plugin),
    "model-package-template.zip": TemplateDefinition("model-package-template.zip", "model-package-template.zip", "model", "标准模型包模板", "已训练模型工件包模板。", _model_package),
    "redis-model-inference-plugin-template.zip": TemplateDefinition("redis-model-inference-plugin-template.zip", "redis-model-inference-plugin-template.zip", "plugin", "Redis + 模型推理模板", "Redis 输入绑定 + context.model 推理模板。", _redis_model_plugin),
    "redis-read-write-plugin-template.zip": TemplateDefinition("redis-read-write-plugin-template.zip", "redis-read-write-plugin-template.zip", "plugin", "Redis 读取与回写模板", "Redis 单点读取与平台回写模板。", _redis_rw_plugin),
    "tdengine-history-plugin-template.zip": TemplateDefinition("tdengine-history-plugin-template.zip", "tdengine-history-plugin-template.zip", "plugin", "TDengine 历史读取模板", "TDengine 历史数据读取模板。", _tdengine_history_plugin),
    "tdengine-model-update-trainer-template.zip": TemplateDefinition("tdengine-model-update-trainer-template.zip", "tdengine-model-update-trainer-template.zip", "plugin", "TDengine 模型更新训练模板", "模型更新任务专用模板：由平台读取 TDengine 历史窗口并注入 training_window。", _tdengine_model_update_trainer_plugin),
    "python-extension-module-plugin-template.zip": TemplateDefinition("python-extension-module-plugin-template.zip", "python-extension-module-plugin-template.zip", "plugin", "Python 扩展模块插件模板", "CPython .so/.pyd module entry 模板，需在目标环境编译后上传。", _python_extension_module_plugin),
}


@router.get("/templates")
def list_templates(principal: Principal = Depends(require_permission("package.read"))) -> dict[str, object]:
    return {
        "items": [
            {
                "name": item.name,
                "filename": item.filename,
                "category": item.category,
                "title": item.title,
                "description": item.description,
                "download_url": f"/api/v1/templates/{item.name}",
            }
            for key, item in sorted(_TEMPLATES.items())
            if key == item.name
        ]
    }


@router.get("/templates/{template_name}")
def download_template(template_name: str, principal: Principal = Depends(require_permission("package.read"))) -> Response:
    item = _TEMPLATES.get(template_name)
    if item is None:
        raise HTTPException(status_code=404, detail=f"template not found: {template_name}")
    return Response(
        content=item.builder(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{item.filename}"', "Cache-Control": "no-store"},
    )
