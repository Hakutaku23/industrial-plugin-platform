from __future__ import annotations

import io
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


def _zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _python_function_plugin() -> bytes:
    return _zip({
        "manifest.yaml": """apiVersion: plugin.platform/v1\nkind: PluginPackage\nmetadata:\n  name: python-function-template\n  displayName: Python Function Template\n  version: 0.1.0\n  author: local\n  description: Basic Python function plugin template.\nspec:\n  pluginType: python\n  packageFormat: zip\n  entry:\n    mode: function\n    type: file\n    file: main.py\n    callable: run\n  runtime:\n    pythonVersion: '3.11'\n    timeoutSec: 30\n    memoryMB: 512\n    workingDir: .\n  schedule:\n    type: manual\n  inputs:\n    - name: input\n      type: number\n      required: true\n  outputs:\n    - name: result\n      type: number\n      required: true\n      writable: true\n  permissions:\n    network: false\n    filesystem: scoped\n    writeback: true\n    subprocess: false\ncompatibility:\n  platformApi: '>=0.2.0'\n  runnerApi: runner-task/v2\n  supportedEnvironments: [dev, factory]\n""",
        "main.py": """def run(payload):\n    value = float(payload.get('inputs', {}).get('input', 0))\n    return {'status': 'success', 'outputs': {'result': value}, 'metrics': {}, 'logs': []}\n""",
        "README.md": "# Python 函数插件模板\n\n上传 zip 后绑定输入输出即可运行。\n",
    })


def _model_package() -> bytes:
    return _zip({
        "manifest.yaml": """schema: ipp-model/v1\nmodel:\n  name: my-model\n  version: 20260101-001\n  framework: sklearn\n  task_type: regression\n  entry_artifact: model\n  description: Replace placeholder artifacts before upload.\nmodel_family:\n  family_fingerprint: mf_replace_with_your_model_family\nruntime_contract:\n  managed_by_plugin: true\nartifacts:\n  model:\n    path: artifacts/model.placeholder\n    type: user_defined_model\n  x_scaler:\n    path: artifacts/x_scaler.placeholder\n    type: user_defined_scaler\nmetrics:\n  note: put model metrics in metrics.json\n""",
        "checksums.json": "{\n  \"schema\": \"ipp-model-checksums/v1\",\n  \"files\": {}\n}\n",
        "metrics.json": "{\n  \"schema\": \"ipp-model-metrics/v1\",\n  \"metrics\": {},\n  \"metrics_completeness\": {\"reported\": false}\n}\n",
        "artifacts/model.placeholder": "replace with model file\n",
        "artifacts/x_scaler.placeholder": "replace with scaler file\n",
        "README.md": "# 模型包模板\n\n模型名称、版本、family_fingerprint 和 artifacts 均由 manifest.yaml 声明。\n",
    })


def _redis_model_plugin() -> bytes:
    return _zip({
        "manifest.yaml": """apiVersion: plugin.platform/v2\nkind: PluginPackage\nmetadata:\n  name: redis-model-inference-template\n  displayName: Redis Model Inference Template\n  version: 0.1.0\n  author: local\n  description: Redis inputs + context.model artifacts inference template.\nmodelDependency:\n  required: true\n  familyFingerprint: mf_replace_with_your_model_family\n  requiredArtifacts: [model, x_scaler]\nspec:\n  pluginType: python\n  packageFormat: zip\n  entry:\n    mode: function\n    type: file\n    file: main.py\n    callable: run\n  runtime:\n    pythonVersion: '3.11'\n    timeoutSec: 60\n    memoryMB: 2048\n    workingDir: .\n  schedule:\n    type: manual\n  inputs:\n    - name: input_014\n      type: number\n      required: true\n    - name: input_015\n      type: number\n      required: true\n  outputs:\n    - name: predict\n      type: number\n      required: true\n      writable: true\n  permissions:\n    network: false\n    filesystem: scoped\n    writeback: true\n    subprocess: false\ncompatibility:\n  platformApi: '>=0.2.0'\n  runnerApi: runner-task/v2\n  supportedEnvironments: [dev, factory]\n""",
        "main.py": """import json\nfrom pathlib import Path\n\n\ndef run(payload):\n    inputs = payload.get('inputs', {})\n    model_ctx = payload.get('context', {}).get('model') or {}\n    artifacts = model_ctx.get('artifacts') or {}\n    model_path = artifacts.get('model', {}).get('path')\n    x_scaler_path = artifacts.get('x_scaler', {}).get('path')\n    # Replace this block with pickle/joblib loading and inference.\n    value = float(inputs.get('input_014', 0)) + float(inputs.get('input_015', 0))\n    return {\n        'status': 'success',\n        'outputs': {'predict': value},\n        'metrics': {'model_path': str(model_path), 'x_scaler_path': str(x_scaler_path)},\n        'logs': ['redis model inference template completed'],\n    }\n""",
        "requirements.txt": "numpy\nscikit-learn\njoblib\n",
        "README.md": "# Redis + 模型推理插件模板\n\n平台负责 Redis 输入绑定和模型物化，插件只读取 payload.inputs 与 payload.context.model.artifacts。\n",
    })


def _redis_rw_plugin() -> bytes:
    return _zip({"manifest.yaml": """apiVersion: plugin.platform/v1\nkind: PluginPackage\nmetadata:\n  name: redis-read-write-template\n  displayName: Redis Read Write Template\n  version: 0.1.0\n  author: local\n  description: Redis input and writeback template.\nspec:\n  pluginType: python\n  packageFormat: zip\n  entry:\n    mode: function\n    file: main.py\n    callable: run\n  runtime:\n    timeoutSec: 30\n    memoryMB: 512\n  schedule:\n    type: manual\n  inputs:\n    - name: input\n      type: number\n      required: true\n  outputs:\n    - name: output\n      type: number\n      required: true\n      writable: true\n  permissions:\n    network: false\n    filesystem: scoped\n    writeback: true\n    subprocess: false\ncompatibility:\n  platformApi: '>=0.2.0'\n  runnerApi: runner-task/v2\n""", "main.py": "def run(payload):\n    return {'status': 'success', 'outputs': {'output': payload['inputs'].get('input')}, 'metrics': {}, 'logs': []}\n"})


def _tdengine_history_plugin() -> bytes:
    return _zip({"manifest.yaml": """apiVersion: plugin.platform/v1\nkind: PluginPackage\nmetadata:\n  name: tdengine-history-template\n  displayName: TDengine History Template\n  version: 0.1.0\n  author: local\n  description: TDengine history input template.\nspec:\n  pluginType: python\n  packageFormat: zip\n  entry:\n    mode: function\n    file: main.py\n    callable: run\n  runtime:\n    timeoutSec: 60\n    memoryMB: 1024\n  schedule:\n    type: manual\n  inputs:\n    - name: history_window\n      type: object\n      required: true\n  outputs:\n    - name: summary\n      type: object\n      required: true\n  permissions:\n    network: false\n    filesystem: scoped\n    writeback: false\n    subprocess: false\ncompatibility:\n  platformApi: '>=0.2.0'\n  runnerApi: runner-task/v2\n""", "main.py": "def run(payload):\n    rows = payload.get('inputs', {}).get('history_window', [])\n    return {'status': 'success', 'outputs': {'summary': {'rows': len(rows) if isinstance(rows, list) else 0}}, 'metrics': {}, 'logs': []}\n"})


_TEMPLATES = {
    "python-function-plugin-template.zip": TemplateDefinition("python-function-plugin-template.zip", "python-function-plugin-template.zip", "plugin", "Python 函数插件模板", "最小函数式插件模板。", _python_function_plugin),
    "python-function-package.zip": TemplateDefinition("python-function-package.zip", "python-function-plugin-template.zip", "plugin", "Python 函数插件模板", "旧地址兼容。", _python_function_plugin),
    "model-package-template.zip": TemplateDefinition("model-package-template.zip", "model-package-template.zip", "model", "标准模型包模板", "已训练模型工件包模板。", _model_package),
    "redis-model-inference-plugin-template.zip": TemplateDefinition("redis-model-inference-plugin-template.zip", "redis-model-inference-plugin-template.zip", "plugin", "Redis + 模型推理模板", "Redis 输入绑定 + context.model 推理模板。", _redis_model_plugin),
    "redis-read-write-plugin-template.zip": TemplateDefinition("redis-read-write-plugin-template.zip", "redis-read-write-plugin-template.zip", "plugin", "Redis 读取与回写模板", "Redis 单点读取与平台回写模板。", _redis_rw_plugin),
    "tdengine-history-plugin-template.zip": TemplateDefinition("tdengine-history-plugin-template.zip", "tdengine-history-plugin-template.zip", "plugin", "TDengine 历史读取模板", "TDengine history input 模板。", _tdengine_history_plugin),
}


@router.get("/templates")
def list_templates(principal: Principal = Depends(require_permission("package.read"))) -> dict[str, object]:
    return {
        "items": [
            {"name": item.name, "filename": item.filename, "category": item.category, "title": item.title, "description": item.description, "download_url": f"/api/v1/templates/{item.name}"}
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
