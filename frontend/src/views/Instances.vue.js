/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/template-helpers.d.ts" />
/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/props-fallback.d.ts" />
import { onMounted, onUnmounted, ref } from 'vue';
import { deleteInstance, listDataSources, listInstances, listPackages, listPackageVersions, listRuns, runInstance, saveInstance, updateInstanceSchedule, } from '../api/packages';
const dataSources = ref([]);
const pluginPackages = ref([]);
const pluginVersions = ref([]);
const instances = ref([]);
const recentRuns = ref([]);
const runResults = ref({});
const loading = ref(false);
const saving = ref(false);
const runningId = ref(null);
const operatingId = ref(null);
const editingInstanceId = ref(null);
const error = ref('');
const form = ref({
    name: 'demo-instance',
    package_name: '',
    version: '',
    writeback_enabled: false,
    schedule_enabled: false,
    schedule_interval_sec: 30,
    configText: '{}',
});
const inputBindings = ref([]);
const outputBindings = ref([]);
let refreshTimer;
async function loadAll() {
    loading.value = true;
    error.value = '';
    try {
        pluginPackages.value = await listPackages();
        dataSources.value = await listDataSources();
        instances.value = await listInstances();
        recentRuns.value = await listRuns();
        await applyDefaultPlugin();
        applyDefaultDataSource();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例数据加载失败';
    }
    finally {
        loading.value = false;
    }
}
async function loadPluginVersions(packageName) {
    pluginVersions.value = packageName ? await listPackageVersions(packageName) : [];
}
async function applyDefaultPlugin() {
    const currentPackage = pluginPackages.value.find((item) => item.name === form.value.package_name);
    const selectedPackage = currentPackage ?? pluginPackages.value[0];
    if (!selectedPackage) {
        form.value.package_name = '';
        form.value.version = '';
        pluginVersions.value = [];
        return;
    }
    form.value.package_name = selectedPackage.name;
    await loadPluginVersions(selectedPackage.name);
    const currentVersion = pluginVersions.value.find((item) => item.version === form.value.version);
    form.value.version =
        currentVersion?.version ?? selectedPackage.latest_version ?? pluginVersions.value[0]?.version ?? '';
}
async function onPackageChange() {
    await loadPluginVersions(form.value.package_name);
    form.value.version = pluginVersions.value[0]?.version ?? '';
}
function applyDefaultDataSource() {
    const defaultId = dataSources.value[0] ? String(dataSources.value[0].id) : '';
    for (const binding of inputBindings.value) {
        if (!binding.data_source_id) {
            binding.data_source_id = defaultId;
        }
    }
    for (const binding of outputBindings.value) {
        if (!binding.data_source_id) {
            binding.data_source_id = defaultId;
        }
    }
}
function addInputBinding() {
    inputBindings.value.push({
        input_name: '',
        data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
        source_tag: '',
    });
}
function removeInputBinding(index) {
    inputBindings.value.splice(index, 1);
}
function addOutputBinding() {
    outputBindings.value.push({
        output_name: '',
        data_source_id: dataSources.value[0] ? String(dataSources.value[0].id) : '',
        target_tag: '',
        dry_run: true,
    });
}
function removeOutputBinding(index) {
    outputBindings.value.splice(index, 1);
}
async function submit() {
    saving.value = true;
    error.value = '';
    try {
        if (!form.value.name.trim()) {
            throw new Error('请填写实例名');
        }
        if (!form.value.package_name || !form.value.version) {
            throw new Error('请选择插件和版本');
        }
        const normalizedInputBindings = inputBindings.value
            .filter((binding) => binding.input_name.trim() && binding.data_source_id && binding.source_tag.trim())
            .map((binding) => ({
            input_name: binding.input_name.trim(),
            data_source_id: Number(binding.data_source_id),
            source_tag: binding.source_tag.trim(),
        }));
        const normalizedOutputBindings = outputBindings.value
            .filter((binding) => binding.output_name.trim() && binding.data_source_id && binding.target_tag.trim())
            .map((binding) => ({
            output_name: binding.output_name.trim(),
            data_source_id: Number(binding.data_source_id),
            target_tag: binding.target_tag.trim(),
            dry_run: binding.dry_run,
        }));
        const duplicateInput = duplicateBindingKey(normalizedInputBindings.map((binding) => `${binding.data_source_id}:${binding.source_tag}`));
        if (duplicateInput) {
            throw new Error(`读取绑定重复：${duplicateInput}`);
        }
        const duplicateOutput = duplicateBindingKey(normalizedOutputBindings.map((binding) => `${binding.data_source_id}:${binding.target_tag}`));
        if (duplicateOutput) {
            throw new Error(`回写绑定重复：${duplicateOutput}`);
        }
        await saveInstance({
            id: editingInstanceId.value,
            name: form.value.name.trim(),
            package_name: form.value.package_name,
            version: form.value.version,
            input_bindings: normalizedInputBindings,
            output_bindings: normalizedOutputBindings,
            config: JSON.parse(form.value.configText),
            writeback_enabled: form.value.writeback_enabled,
            schedule_enabled: form.value.schedule_enabled,
            schedule_interval_sec: Number(form.value.schedule_interval_sec) || 30,
        });
        await loadAll();
        resetForm();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例保存失败';
    }
    finally {
        saving.value = false;
    }
}
function duplicateBindingKey(keys) {
    const seen = new Set();
    for (const key of keys) {
        if (seen.has(key)) {
            return key;
        }
        seen.add(key);
    }
    return '';
}
async function run(instance) {
    runningId.value = instance.id;
    error.value = '';
    try {
        const result = await runInstance(instance.id);
        runResults.value = { ...runResults.value, [instance.id]: result };
        recentRuns.value = await listRuns();
        await loadAll();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例运行失败';
    }
    finally {
        runningId.value = null;
    }
}
async function stopSchedule(instance) {
    operatingId.value = instance.id;
    error.value = '';
    try {
        await updateInstanceSchedule(instance.id, { enabled: false });
        await loadAll();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例停止失败';
    }
    finally {
        operatingId.value = null;
    }
}
async function startSchedule(instance) {
    operatingId.value = instance.id;
    error.value = '';
    try {
        await updateInstanceSchedule(instance.id, {
            enabled: true,
            interval_sec: instance.schedule_interval_sec || 30,
        });
        await loadAll();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例定时启动失败';
    }
    finally {
        operatingId.value = null;
    }
}
async function removeInstance(instance) {
    if (!window.confirm(`确认删除实例 ${instance.name}？`)) {
        return;
    }
    operatingId.value = instance.id;
    error.value = '';
    try {
        await deleteInstance(instance.id);
        if (editingInstanceId.value === instance.id) {
            resetForm();
        }
        await loadAll();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '实例删除失败';
    }
    finally {
        operatingId.value = null;
    }
}
async function editInstance(instance) {
    editingInstanceId.value = instance.id;
    form.value = {
        name: instance.name,
        package_name: instance.package_name,
        version: instance.version,
        writeback_enabled: instance.writeback_enabled,
        schedule_enabled: instance.schedule_enabled,
        schedule_interval_sec: instance.schedule_interval_sec || 30,
        configText: JSON.stringify(instance.config ?? {}, null, 2),
    };
    await loadPluginVersions(instance.package_name);
    inputBindings.value = instance.input_bindings.map((binding) => ({
        input_name: stringValue(binding.input_name),
        data_source_id: stringValue(binding.data_source_id),
        source_tag: stringValue(binding.source_tag),
    }));
    outputBindings.value = instance.output_bindings.map((binding) => ({
        output_name: stringValue(binding.output_name),
        data_source_id: stringValue(binding.data_source_id),
        target_tag: stringValue(binding.target_tag),
        dry_run: Boolean(binding.dry_run ?? true),
    }));
}
function resetForm() {
    editingInstanceId.value = null;
    form.value = {
        name: 'demo-instance',
        package_name: pluginPackages.value[0]?.name ?? '',
        version: pluginPackages.value[0]?.latest_version ?? '',
        writeback_enabled: false,
        schedule_enabled: false,
        schedule_interval_sec: 30,
        configText: '{}',
    };
    inputBindings.value = [];
    outputBindings.value = [];
}
function inputOptions(binding, index) {
    const source = findDataSource(binding.data_source_id);
    if (!source) {
        return [];
    }
    return getReadPointOptions(source).filter((point) => !isInputTagSelectedByOtherRow(index, binding.data_source_id, point.tag));
}
function outputOptions(binding, index) {
    const source = findDataSource(binding.data_source_id);
    if (!source) {
        return [];
    }
    return getWritePointOptions(source).filter((point) => !isOutputTagSelectedByOtherRow(index, binding.data_source_id, point.tag));
}
function isInputTagSelectedByOtherRow(index, dataSourceId, tag) {
    return inputBindings.value.some((binding, bindingIndex) => bindingIndex !== index && binding.data_source_id === dataSourceId && binding.source_tag === tag);
}
function isOutputTagSelectedByOtherRow(index, dataSourceId, tag) {
    return outputBindings.value.some((binding, bindingIndex) => bindingIndex !== index && binding.data_source_id === dataSourceId && binding.target_tag === tag);
}
function findDataSource(dataSourceId) {
    return dataSources.value.find((item) => String(item.id) === String(dataSourceId));
}
function stringify(value) {
    return JSON.stringify(value, null, 2);
}
function formatTime(value) {
    if (!value) {
        return '未计划';
    }
    return new Date(value).toLocaleString();
}
function recentRunsForInstance(instance) {
    return recentRuns.value
        .filter((run) => {
        if (run.instance_id === instance.id) {
            return true;
        }
        return (run.instance_id === null &&
            run.package_name === instance.package_name &&
            run.version === instance.version);
    })
        .slice(0, 3);
}
function getReadPointOptions(source) {
    const catalog = catalogFromConfig(source);
    if (Array.isArray(catalog)) {
        const points = catalog
            .map((point) => pointOption(point, ['readTag', 'read_tag'], ['canRead', 'can_read']))
            .filter((point) => Boolean(point));
        if (points.length > 0) {
            return points;
        }
    }
    const configured = tagListFromConfig(source, 'readTags', 'read_tags');
    if (configured.length > 0) {
        return configured.map((tag) => ({ label: tag, tag }));
    }
    if (source.connector_type === 'mock' && isRecord(source.config.points)) {
        return Object.keys(source.config.points).map((tag) => ({ label: tag, tag }));
    }
    return [];
}
function getWritePointOptions(source) {
    const catalog = catalogFromConfig(source);
    if (Array.isArray(catalog)) {
        const points = catalog
            .map((point) => pointOption(point, ['writeTag', 'write_tag'], ['canWrite', 'can_write']))
            .filter((point) => Boolean(point));
        if (points.length > 0) {
            return points;
        }
    }
    const configured = tagListFromConfig(source, 'writeTags', 'write_tags');
    if (configured.length > 0) {
        return configured.map((tag) => ({ label: tag, tag }));
    }
    if (source.connector_type === 'mock' && isRecord(source.config.points)) {
        return Object.keys(source.config.points).map((tag) => ({ label: tag, tag }));
    }
    return [];
}
function catalogFromConfig(source) {
    return source.config.pointCatalog ?? source.config.point_catalog;
}
function tagListFromConfig(source, camelKey, snakeKey) {
    const camel = arrayOfStrings(source.config[camelKey]);
    return camel.length > 0 ? camel : arrayOfStrings(source.config[snakeKey]);
}
function pointOption(point, tagFields, permissionFields) {
    if (!isRecord(point) || !isAllowed(point, permissionFields)) {
        return null;
    }
    const tag = tagFields
        .map((field) => point[field])
        .find((value) => typeof value === 'string' && value.length > 0);
    if (!tag) {
        return null;
    }
    const pointClass = stringField(point, ['class', 'pointClass', 'point_class']) || '未分类';
    return {
        label: `${pointClass} / ${tag}`,
        tag,
    };
}
function isAllowed(record, fields) {
    const configured = fields
        .map((field) => record[field])
        .find((value) => typeof value === 'boolean');
    return configured ?? true;
}
function stringField(record, fields) {
    return fields
        .map((field) => record[field])
        .find((value) => typeof value === 'string' && value.length > 0);
}
function stringValue(value) {
    if (value === null || value === undefined) {
        return '';
    }
    return String(value);
}
function arrayOfStrings(value) {
    return Array.isArray(value) ? value.filter((item) => typeof item === 'string') : [];
}
function isRecord(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}
onMounted(() => {
    loadAll();
    refreshTimer = window.setInterval(() => {
        loadAll();
    }, 5000);
});
onUnmounted(() => {
    if (refreshTimer !== undefined) {
        window.clearInterval(refreshTimer);
    }
});
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
__VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
    ...{ onChange: (__VLS_ctx.onPackageChange) },
    value: (__VLS_ctx.form.package_name),
});
__VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
    value: "",
});
for (const [plugin] of __VLS_vFor((__VLS_ctx.pluginPackages))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
        key: (plugin.id),
        value: (plugin.name),
    });
    (plugin.display_name || plugin.name);
    (plugin.name);
    // @ts-ignore
    [loadAll, loading, loading, error, error, submit, form, form, onPackageChange, pluginPackages,];
}
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
    value: (__VLS_ctx.form.version),
    disabled: (__VLS_ctx.pluginVersions.length === 0),
});
__VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
    value: "",
});
for (const [version] of __VLS_vFor((__VLS_ctx.pluginVersions))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
        key: (version.id),
        value: (version.version),
    });
    (version.version);
    // @ts-ignore
    [form, pluginVersions, pluginVersions,];
}
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    type: "number",
    min: "5",
    step: "1",
});
(__VLS_ctx.form.schedule_interval_sec);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "checkbox-line" },
});
/** @type {__VLS_StyleScopedClasses['checkbox-line']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    type: "checkbox",
});
(__VLS_ctx.form.schedule_enabled);
__VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
    ...{ class: "checkbox-line" },
});
/** @type {__VLS_StyleScopedClasses['checkbox-line']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.input)({
    type: "checkbox",
});
(__VLS_ctx.form.writeback_enabled);
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "wide-field binding-list" },
});
/** @type {__VLS_StyleScopedClasses['wide-field']} */ ;
/** @type {__VLS_StyleScopedClasses['binding-list']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "section-title" },
});
/** @type {__VLS_StyleScopedClasses['section-title']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    ...{ onClick: (__VLS_ctx.addInputBinding) },
    type: "button",
    ...{ class: "secondary-button" },
});
/** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "binding-table" },
});
/** @type {__VLS_StyleScopedClasses['binding-table']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "binding-table-head binding-row" },
});
/** @type {__VLS_StyleScopedClasses['binding-table-head']} */ ;
/** @type {__VLS_StyleScopedClasses['binding-row']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
for (const [binding, index] of __VLS_vFor((__VLS_ctx.inputBindings))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        key: (index),
        ...{ class: "binding-row" },
    });
    /** @type {__VLS_StyleScopedClasses['binding-row']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        'aria-label': "插件输入名",
        placeholder: "如 value、temperature",
    });
    (binding.input_name);
    __VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
        ...{ onChange: (...[$event]) => {
                binding.source_tag = '';
                // @ts-ignore
                [form, form, form, addInputBinding, inputBindings,];
            } },
        value: (binding.data_source_id),
        'aria-label': "读取数据源",
    });
    __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
        value: "",
    });
    for (const [source] of __VLS_vFor((__VLS_ctx.dataSources))) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
            key: (source.id),
            value: (source.id),
        });
        (source.name);
        // @ts-ignore
        [dataSources,];
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
        value: (binding.source_tag),
        'aria-label': "读取位点",
    });
    __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
        value: "",
    });
    for (const [point] of __VLS_vFor((__VLS_ctx.inputOptions(binding, index)))) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
            key: (point.tag),
            value: (point.tag),
        });
        (point.label);
        // @ts-ignore
        [inputOptions,];
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        'aria-label': "手动读取 Redis Key",
        placeholder: "如 sthb:DCS_AO_RTO_014_AI",
    });
    (binding.source_tag);
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.removeInputBinding(index);
                // @ts-ignore
                [removeInputBinding,];
            } },
        type: "button",
        ...{ class: "danger-button" },
    });
    /** @type {__VLS_StyleScopedClasses['danger-button']} */ ;
    // @ts-ignore
    [];
}
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "wide-field binding-list" },
});
/** @type {__VLS_StyleScopedClasses['wide-field']} */ ;
/** @type {__VLS_StyleScopedClasses['binding-list']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "section-title" },
});
/** @type {__VLS_StyleScopedClasses['section-title']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    ...{ onClick: (__VLS_ctx.addOutputBinding) },
    type: "button",
    ...{ class: "secondary-button" },
});
/** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "binding-table" },
});
/** @type {__VLS_StyleScopedClasses['binding-table']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "binding-table-head binding-row binding-row-output" },
});
/** @type {__VLS_StyleScopedClasses['binding-table-head']} */ ;
/** @type {__VLS_StyleScopedClasses['binding-row']} */ ;
/** @type {__VLS_StyleScopedClasses['binding-row-output']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
for (const [binding, index] of __VLS_vFor((__VLS_ctx.outputBindings))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        key: (index),
        ...{ class: "binding-row binding-row-output" },
    });
    /** @type {__VLS_StyleScopedClasses['binding-row']} */ ;
    /** @type {__VLS_StyleScopedClasses['binding-row-output']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        'aria-label': "插件输出名",
        placeholder: "如 doubled、setpoint",
    });
    (binding.output_name);
    __VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
        ...{ onChange: (...[$event]) => {
                binding.target_tag = '';
                // @ts-ignore
                [addOutputBinding, outputBindings,];
            } },
        value: (binding.data_source_id),
        'aria-label': "回写数据源",
    });
    __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
        value: "",
    });
    for (const [source] of __VLS_vFor((__VLS_ctx.dataSources))) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
            key: (source.id),
            value: (source.id),
        });
        (source.name);
        // @ts-ignore
        [dataSources,];
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.select, __VLS_intrinsics.select)({
        value: (binding.target_tag),
        'aria-label': "回写位点",
    });
    __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
        value: "",
    });
    for (const [point] of __VLS_vFor((__VLS_ctx.outputOptions(binding, index)))) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.option, __VLS_intrinsics.option)({
            key: (point.tag),
            value: (point.tag),
        });
        (point.label);
        // @ts-ignore
        [outputOptions,];
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        'aria-label': "手动回写 Redis Key",
        placeholder: "如 sthb:DCS_AO_RTO_014_AO",
    });
    (binding.target_tag);
    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
        ...{ class: "inline-check" },
    });
    /** @type {__VLS_StyleScopedClasses['inline-check']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        type: "checkbox",
    });
    (binding.dry_run);
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.removeOutputBinding(index);
                // @ts-ignore
                [removeOutputBinding,];
            } },
        type: "button",
        ...{ class: "danger-button" },
    });
    /** @type {__VLS_StyleScopedClasses['danger-button']} */ ;
    // @ts-ignore
    [];
}
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
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "form-actions wide-field" },
});
/** @type {__VLS_StyleScopedClasses['form-actions']} */ ;
/** @type {__VLS_StyleScopedClasses['wide-field']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    type: "submit",
    disabled: (__VLS_ctx.saving),
});
(__VLS_ctx.saving ? '保存中' : __VLS_ctx.editingInstanceId ? '保存修改' : '保存实例');
if (__VLS_ctx.editingInstanceId) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (__VLS_ctx.resetForm) },
        type: "button",
        ...{ class: "secondary-button" },
    });
    /** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
}
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
    (instance.writeback_enabled ? '允许真实回写' : '仅 dry-run / 阻断真实回写');
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "package-meta" },
    });
    /** @type {__VLS_StyleScopedClasses['package-meta']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (instance.status);
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (instance.schedule_enabled ? `每 ${instance.schedule_interval_sec} 秒` : '未启用定时');
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "status-grid" },
    });
    /** @type {__VLS_StyleScopedClasses['status-grid']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    (__VLS_ctx.formatTime(instance.last_scheduled_run_at));
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    (__VLS_ctx.formatTime(instance.next_scheduled_run_at));
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "instance-actions" },
    });
    /** @type {__VLS_StyleScopedClasses['instance-actions']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.editInstance(instance);
                // @ts-ignore
                [form, saving, saving, editingInstanceId, editingInstanceId, resetForm, instances, formatTime, formatTime, editInstance,];
            } },
        type: "button",
        ...{ class: "secondary-button" },
    });
    /** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.run(instance);
                // @ts-ignore
                [run,];
            } },
        type: "button",
        ...{ class: "secondary-button" },
        disabled: (__VLS_ctx.runningId === instance.id),
    });
    /** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
    (__VLS_ctx.runningId === instance.id ? '运行中' : '手动运行');
    if (instance.schedule_enabled) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(instance.schedule_enabled))
                        return;
                    __VLS_ctx.stopSchedule(instance);
                    // @ts-ignore
                    [runningId, runningId, stopSchedule,];
                } },
            type: "button",
            ...{ class: "secondary-button" },
            disabled: (__VLS_ctx.operatingId === instance.id),
        });
        /** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
    }
    else {
        __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(instance.schedule_enabled))
                        return;
                    __VLS_ctx.startSchedule(instance);
                    // @ts-ignore
                    [operatingId, startSchedule,];
                } },
            type: "button",
            ...{ class: "secondary-button" },
            disabled: (__VLS_ctx.operatingId === instance.id),
        });
        /** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.removeInstance(instance);
                // @ts-ignore
                [operatingId, removeInstance,];
            } },
        type: "button",
        ...{ class: "danger-button" },
        disabled: (__VLS_ctx.operatingId === instance.id),
    });
    /** @type {__VLS_StyleScopedClasses['danger-button']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.pre, __VLS_intrinsics.pre)({});
    (__VLS_ctx.stringify({ input_bindings: instance.input_bindings, output_bindings: instance.output_bindings }));
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "run-history" },
    });
    /** @type {__VLS_StyleScopedClasses['run-history']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
    if (__VLS_ctx.recentRunsForInstance(instance).length === 0) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "muted" },
        });
        /** @type {__VLS_StyleScopedClasses['muted']} */ ;
    }
    for (const [run] of __VLS_vFor((__VLS_ctx.recentRunsForInstance(instance)))) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            key: (run.run_id),
            ...{ class: "run-history-row" },
        });
        /** @type {__VLS_StyleScopedClasses['run-history-row']} */ ;
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        (run.trigger_type);
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        (run.status);
        __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
        (__VLS_ctx.formatTime(run.finished_at));
        __VLS_asFunctionalElement1(__VLS_intrinsics.code, __VLS_intrinsics.code)({});
        (run.run_id);
        // @ts-ignore
        [formatTime, operatingId, stringify, recentRunsForInstance, recentRunsForInstance,];
    }
    if (__VLS_ctx.runResults[instance.id]) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.pre, __VLS_intrinsics.pre)({});
        (__VLS_ctx.stringify(__VLS_ctx.runResults[instance.id]));
    }
    // @ts-ignore
    [stringify, runResults, runResults,];
}
// @ts-ignore
[];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
