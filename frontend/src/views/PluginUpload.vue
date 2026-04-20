<script setup lang="ts">
import { ref } from 'vue'
import { uploadPackage, type UploadPackageResult } from '../api/packages'

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const result = ref<UploadPackageResult | null>(null)
const error = ref('')

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  result.value = null
  error.value = ''
}

async function submit() {
  if (!selectedFile.value) {
    error.value = '请选择 zip 或 tar.gz 插件包'
    return
  }

  uploading.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await uploadPackage(selectedFile.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '插件包上传失败'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="intro upload-intro">
      <div>
        <p class="eyebrow">Package Registry</p>
        <h2>上传插件包</h2>
        <p>支持 zip 与 tar.gz。包根目录必须包含 manifest.yaml。</p>
      </div>
      <a class="secondary-button template-download" href="/api/v1/templates/python-function-package.zip">
        下载插件模板
      </a>
    </div>

    <div class="template-hint">
      <strong>推荐入口：</strong>
      <span>首次编写插件时，先下载模板，再替换 runtime/main.py 与编译产物。</span>
    </div>

    <form class="upload-form" @submit.prevent="submit">
      <label>
        插件包
        <input type="file" accept=".zip,.gz,.tar.gz" @change="onFileChange" />
      </label>
      <button type="submit" :disabled="uploading">
        {{ uploading ? '上传中' : '上传并校验' }}
      </button>
    </form>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="result" class="result">
      <h3>校验通过</h3>
      <p>
        已登记版本记录。可前往
        <RouterLink to="/packages">插件包列表</RouterLink>
        查看。
      </p>
      <dl>
        <div>
          <dt>名称</dt>
          <dd>{{ result.name }}</dd>
        </div>
        <div>
          <dt>版本</dt>
          <dd>{{ result.version }}</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>{{ result.status }}</dd>
        </div>
        <div>
          <dt>包 ID</dt>
          <dd>{{ result.package_id }}</dd>
        </div>
        <div>
          <dt>版本 ID</dt>
          <dd>{{ result.version_id }}</dd>
        </div>
        <div>
          <dt>审计 ID</dt>
          <dd>{{ result.audit_event_id }}</dd>
        </div>
        <div>
          <dt>摘要</dt>
          <dd>{{ result.digest }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<style scoped>
.upload-intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.template-download {
  text-decoration: none;
  white-space: nowrap;
}

.template-hint {
  margin: 12px 0 16px;
  padding: 12px 14px;
  border: 1px solid #d8e3df;
  border-radius: 8px;
  background: #f7faf9;
  color: #314340;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
