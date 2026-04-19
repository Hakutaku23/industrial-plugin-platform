/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/template-helpers.d.ts" />
/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/props-fallback.d.ts" />
import { onMounted, ref } from 'vue';
import { listDataSources, listInstances, runInstance, saveInstance, } from '../api/packages';
const dataSources = ref([]);
const instances = ref([]);
const runResults = ref({});
const loading = ref(false);
const saving = ref(false);
const runningId = ref(null);
const error = ref('');
const form = ref({
    name: 'demo-instance',
    package_name: 'demo-python-plugin',
    version: '0.1.0',
    input_name: 'value',
    input_data_source_id: '',
    source_tag: 'demo:value',
    output_name: 'doubled',
    output_data_source_id: '',
    target_tag: 'demo:doubled',
    dry_run: true,
    writeback_enabled: false,
    configText: '{}',
});
async function loadAll() {
    loading.value = true;
    error.value = '';
    try {
        dataSources.value = await listDataSources();
        instances.value = await listInstances();
        if (!form.value.input_data_source_id && dataSources.value[0]) {
            form.value.input_data_source_id = String(dataSources.value[0].id);
            form.value.output_data_source_id = String(dataSources.value[0].id);
        }
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例数据加载失败';
    }
    finally {
        loading.value = false;
    }
}
async function submit() {
    saving.value = true;
    error.value = '';
    try {
        await saveInstance({
            name: form.value.name,
            package_name: form.value.package_name,
            version: form.value.version,
            input_bindings: [
                {
                    input_name: form.value.input_name,
                    data_source_id: Number(form.value.input_data_source_id),
                    source_tag: form.value.source_tag,
                },
            ],
            output_bindings: [
                {
                    output_name: form.value.output_name,
                    data_source_id: Number(form.value.output_data_source_id),
                    target_tag: form.value.target_tag,
                    dry_run: form.value.dry_run,
                },
            ],
            config: JSON.parse(form.value.configText),
            writeback_enabled: form.value.writeback_enabled,
        });
        await loadAll();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例保存失败';
    }
    finally {
        saving.value = false;
    }
}
async function run(instance) {
    runningId.value = instance.id;
    error.value = '';
    try {
        const result = await runInstance(instance.id);
        runResults.value = { ...runResults.value, [instance.id]: result };
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例运行失败';
    }
    finally {
        runningId.value = null;
    }
}
function stringify(value) {
    return JSON.stringify(value, null, 2);
}
onMounted(loadAll);
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
    ...{ onClick: (__VLS_ctx.loadAll) },
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
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
(__VLS_ctx.form.package_name);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
(__VLS_ctx.form.version);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
(__VLS_ctx.form.input_name);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
    value: (__VLS_ctx.form.input_data_source_id),
});
for (const [source] of __VLS_vFor((__VLS_ctx.dataSources))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
        key: (source.id),
        value: (source.id),
    });
    (source.name);
    // @ts-ignore
    [loadAll, loading, loading, error, error, submit, form, form, form, form, form, dataSources,];
}
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
(__VLS_ctx.form.source_tag);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
(__VLS_ctx.form.output_name);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
    value: (__VLS_ctx.form.output_data_source_id),
});
for (const [source] of __VLS_vFor((__VLS_ctx.dataSources))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
        key: (source.id),
        value: (source.id),
    });
    (source.name);
    // @ts-ignore
    [form, form, form, dataSources,];
}
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
(__VLS_ctx.form.target_tag);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "checkbox-line" },
});
/** @type {__VLS_StyleScopedClasses['checkbox-line']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    type: "checkbox",
});
(__VLS_ctx.form.dry_run);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "checkbox-line" },
});
/** @type {__VLS_StyleScopedClasses['checkbox-line']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    type: "checkbox",
});
(__VLS_ctx.form.writeback_enabled);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "json-input wide-field" },
});
/** @type {__VLS_StyleScopedClasses['json-input']} */ ;
/** @type {__VLS_StyleScopedClasses['wide-field']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.textarea, __VLS_intrinsics.textarea)({
    value: (__VLS_ctx.form.configText),
    rows: "4",
    spellcheck: "false",
});
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    type: "submit",
    disabled: (__VLS_ctx.saving),
});
(__VLS_ctx.saving ? '保存中' : '保存实例');
for (const [instance] of __VLS_vFor((__VLS_ctx.instances))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        key: (instance.id),
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
    (instance.package_name);
    (instance.version);
    __VLS_asFunctionalElement1(__VLS_intrinsics.h3, __VLS_intrinsics.h3)({});
    (instance.name);
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
    (instance.writeback_enabled ? '允许真实写回' : '仅 dry-run / 阻断写回');
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "package-meta" },
    });
    /** @type {__VLS_StyleScopedClasses['package-meta']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (instance.status);
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.run(instance);
                // @ts-ignore
                [form, form, form, form, saving, saving, instances, run,];
            } },
        type: "button",
        ...{ class: "secondary-button" },
        disabled: (__VLS_ctx.runningId === instance.id),
    });
    /** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
    (__VLS_ctx.runningId === instance.id ? '运行中' : '运行实例');
    __VLS_asFunctionalElement1(__VLS_intrinsics.pre, __VLS_intrinsics.pre)({});
    (__VLS_ctx.stringify({ input_bindings: instance.input_bindings, output_bindings: instance.output_bindings }));
    if (__VLS_ctx.runResults[instance.id]) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.pre, __VLS_intrinsics.pre)({});
        (__VLS_ctx.stringify(__VLS_ctx.runResults[instance.id]));
    }
    // @ts-ignore
    [runningId, runningId, stringify, stringify, runResults, runResults,];
}
// @ts-ignore
[];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
