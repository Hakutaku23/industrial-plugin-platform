from __future__ import annotations

from io import BytesIO
import textwrap
import zipfile


def build_python_function_template_archive() -> bytes:
    files = {
        "manifest.yaml": _manifest_text(),
        "README.md": _readme_text(),
        "runtime/__init__.py": "",
        "runtime/main.py": _main_py_text(),
        "runtime/core_BUILD_ARTIFACT_HERE.txt": _artifact_note_text(),
    }

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def _manifest_text() -> str:
    return textwrap.dedent(
        """
        apiVersion: plugin.platform/v1
        kind: PluginPackage

        metadata:
          name: native-runtime-demo
          displayName: Native Runtime Demo
          version: 0.1.0
          author: your-name
          description: >
            示例插件包骨架。入口函数位于 runtime/main.py，可按需导入同目录下的编译扩展。
          tags:
            - native
            - python

        spec:
          pluginType: python
          packageFormat: zip
          entry:
            mode: function
            file: runtime/main.py
            callable: run
          runtime:
            pythonVersion: match-host-interpreter
            workingDir: .
            timeoutSec: 30
          schedule:
            type: manual
          inputs:
            - name: input_001
              type: number
              required: true
              description: 示例输入 1
            - name: input_014
              type: number
              required: true
              description: 示例输入 2
          outputs:
            - name: output_001
              type: number
              required: true
              description: 示例输出
          permissions:
            network: false
            filesystem: scoped
            writeback: false
            subprocess: false

        compatibility:
          platformApi: ">=0.1.0"
          runnerApi: ">=0.1.0"
          supportedEnvironments:
            - local
        """
    )


def _readme_text() -> str:
    return textwrap.dedent(
        """
        # 插件包模板说明

        该模板对应以下目录结构：

        - manifest.yaml
        - runtime/main.py
        - runtime/__init__.py
        - runtime/core_BUILD_ARTIFACT_HERE.txt

        ## 关于编译扩展

        当前平台对 `.so` / `.pyd` 的支持是“可打包、可跟随上传、运行时按宿主 Python 解释器尝试导入”，
        但不会自动做 ABI、平台、Python 次版本兼容性校验。

        建议实际落包时使用如下结构：

        - manifest.yaml
        - runtime/main.py
        - runtime/core.so        # Linux / macOS 常见命名
          或
        - runtime/core.pyd       # Windows 常见命名

        在 `runtime/main.py` 中建议使用绝对导入：

        ```python
        from runtime import core as native_core
        ```

        不建议使用相对导入：

        ```python
        from . import core
        ```

        因为当前 runner 会把入口文件作为一个独立模块加载，而不是按包模块加载。

        ## 你需要自行保证

        1. 编译产物与部署机器的操作系统一致
        2. 编译产物与运行时 Python 版本 / ABI 一致
        3. 编译产物依赖的系统动态库在目标机器上可用
        """
    )


def _main_py_text() -> str:
    return textwrap.dedent(
        """
        from __future__ import annotations

        from typing import Any

        try:
            from runtime import core as native_core
        except Exception:  # noqa: BLE001
            native_core = None


        def _require_input(inputs: dict[str, Any], name: str) -> Any:
            if name not in inputs:
                raise ValueError(f"missing input: {name}")
            return inputs[name]


        def run(payload: dict[str, Any]) -> dict[str, Any]:
            inputs = payload.get("inputs", {})
            input_001 = _require_input(inputs, "input_001")
            input_014 = _require_input(inputs, "input_014")

            logs: list[str] = []

            if native_core is None:
                logs.append("native extension not found, fallback to pure python demo path")
                output_001 = float(input_001) + float(input_014)
            else:
                logs.append("native extension loaded from runtime/core(.so|.pyd)")  
                output_001 = native_core.compute(float(input_001), float(input_014))

            return {
                "status": "success",
                "outputs": {
                    "output_001": output_001,
                },
                "logs": logs,
                "metrics": {},
            }
        """
    )


def _artifact_note_text() -> str:
    return textwrap.dedent(
        """
        将该占位文件替换为你的编译扩展产物：

        - Linux / macOS: core.so
        - Windows: core.pyd

        建议在 main.py 中通过如下方式导入：

            from runtime import core as native_core

        如果你的扩展名称不是 core，请同步修改 main.py。
        """
    )
