/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/template-helpers.d.ts" />
/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/props-fallback.d.ts" />
import { onMounted, ref } from 'vue';
import { listDataSources, saveDataSource } from '../api/packages';
const dataSources = ref([]);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const form = ref({
    name: 'mock-line-a',
    connector_type: 'mock',
    configText: JSON.stringify({ points: { 'demo:value': 21 } }, null, 2),
    read_enabled: true,
    write_enabled: true,
});
async function loadDataSources() {
    loading.value = true;
    error.value = '';
    try {
        dataSources.value = await listDataSources();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '数据源列表加载失败';
    }
    finally {
        loading.value = false;
    }
}
function useTemplate(type) {
    form.value.connector_type = type;
    form.value.configText =
        type === 'mock'
            ? JSON.stringify({ points: { 'demo:value': 21 } }, null, 2)
            : JSON.stringify({
                host: '127.0.0.1',
                port: 6379,
                db: 0,
                keyPrefix: '',
            }, null, 2);
}
async function submit() {
    saving.value = true;
    error.value = '';
    try {
        await saveDataSource({
            name: form.value.name,
            connector_type: form.value.connector_type,
            config: JSON.parse(form.value.configText),
            read_enabled: form.value.read_enabled,
            write_enabled: form.value.write_enabled,
        });
        await loadDataSources();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '数据源保存失败';
    }
    finally {
        saving.value = false;
    }
}
function stringify(value) {
    return JSON.stringify(value, null, 2);
}
onMounted(loadDataSources);
const __VLS_ctx = {
    ...{},
    ...{},
};
let __VLS_components;
let __VLS_intrinsics;
let __VLS_directives;
__VLS_asFunctionalElement1(__VLS_intrinsics.section, __VLS_intrinsics.section)({
    ...{ class: "panel" },
});
/** @type {__VLS_StyleScopedClasses['panel']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "intro page-heading" },
});
/** @type {__VLS_StyleScopedClasses['intro']} */ ;
/** @type {__VLS_StyleScopedClasses['page-heading']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
    ...{ class: "eyebrow" },
});
/** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.h2, __VLS_intrinsics.h2)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    ...{ onClick: (__VLS_ctx.loadDataSources) },
    type: "button",
    ...{ class: "secondary-button" },
    disabled: (__VLS_ctx.loading),
});
/** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
(__VLS_ctx.loading ? '刷新中' : '刷新');
if (__VLS_ctx.error) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
        ...{ class: "error" },
    });
    /** @type {__VLS_StyleScopedClasses['error']} */ ;
    (__VLS_ctx.error);
}
__VLS_asFunctionalElement1(__VLS_intrinsics.form, __VLS_intrinsics.form)({
    ...{ onSubmit: (__VLS_ctx.submit) },
    ...{ class: "config-form" },
});
/** @type {__VLS_StyleScopedClasses['config-form']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
(__VLS_ctx.form.name);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
    ...{ onChange: (...[$event]) => {
            __VLS_ctx.useTemplate(__VLS_ctx.form.connector_type);
            // @ts-ignore
            [loadDataSources, loading, loading, error, error, submit, form, form, useTemplate,];
        } },
    value: (__VLS_ctx.form.connector_type),
});
__VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
    value: "mock",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
    value: "redis",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "checkbox-line" },
});
/** @type {__VLS_StyleScopedClasses['checkbox-line']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    type: "checkbox",
});
(__VLS_ctx.form.read_enabled);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "checkbox-line" },
});
/** @type {__VLS_StyleScopedClasses['checkbox-line']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    type: "checkbox",
});
(__VLS_ctx.form.write_enabled);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "json-input wide-field" },
});
/** @type {__VLS_StyleScopedClasses['json-input']} */ ;
/** @type {__VLS_StyleScopedClasses['wide-field']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.textarea, __VLS_intrinsics.textarea)({
    value: (__VLS_ctx.form.configText),
    rows: "8",
    spellcheck: "false",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    type: "submit",
    disabled: (__VLS_ctx.saving),
});
(__VLS_ctx.saving ? '保存中' : '保存数据源');
for (const [source] of __VLS_vFor((__VLS_ctx.dataSources))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        key: (source.id),
        ...{ class: "package-row" },
    });
    /** @type {__VLS_StyleScopedClasses['package-row']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "package-main" },
    });
    /** @type {__VLS_StyleScopedClasses['package-main']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
        ...{ class: "eyebrow" },
    });
    /** @type {__VLS_StyleScopedClasses['eyebrow']} */ ;
    (source.connector_type);
    __VLS_asFunctionalElement1(__VLS_intrinsics.h3, __VLS_intrinsics.h3)({});
    (source.name);
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
    (source.read_enabled ? '可读取' : '不可读取');
    (source.write_enabled ? '可写回' : '不可写回');
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "package-meta" },
    });
    /** @type {__VLS_StyleScopedClasses['package-meta']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (source.status);
    __VLS_asFunctionalElement1(__VLS_intrinsics.pre, __VLS_intrinsics.pre)({});
    (__VLS_ctx.stringify(source.config));
    // @ts-ignore
    [form, form, form, form, saving, saving, dataSources, stringify,];
}
// @ts-ignore
[];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
