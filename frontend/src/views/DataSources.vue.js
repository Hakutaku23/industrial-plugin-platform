/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/template-helpers.d.ts" />
/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/props-fallback.d.ts" />
import { onMounted, ref } from 'vue';
import { deleteDataSource, listDataSources, saveDataSource, } from '../api/packages';
const dataSources = ref([]);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const form = ref({
    name: 'mock-line-a',
    connector_type: 'mock',
    host: '127.0.0.1',
    port: 6379,
    db: 0,
    keyPrefix: '',
    read_enabled: true,
    write_enabled: true,
});
const points = ref([
    {
        pointClass: 'demo',
        readEnabled: true,
        readTag: 'demo:value',
        writeEnabled: true,
        writeTag: 'demo:doubled',
        mockValue: '21',
    },
]);
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
function addPoint() {
    points.value.push({
        pointClass: '',
        readEnabled: true,
        readTag: '',
        writeEnabled: false,
        writeTag: '',
        mockValue: '',
    });
}
function removePoint(index) {
    points.value.splice(index, 1);
}
function disableRead(point) {
    if (!point.readEnabled) {
        point.readTag = '';
        point.mockValue = '';
    }
}
function disableWrite(point) {
    if (!point.writeEnabled) {
        point.writeTag = '';
    }
}
function buildConfig() {
    const normalizedPoints = points.value
        .map((point) => ({
        pointClass: point.pointClass.trim(),
        canRead: point.readEnabled,
        readTag: point.readEnabled ? point.readTag.trim() : '',
        canWrite: point.writeEnabled,
        writeTag: point.writeEnabled ? point.writeTag.trim() : '',
        mockValue: point.readEnabled ? point.mockValue.trim() : '',
    }))
        .filter((point) => point.pointClass || point.readTag || point.writeTag);
    const readTags = normalizedPoints
        .filter((point) => point.canRead && point.readTag)
        .map((point) => point.readTag);
    const writeTags = normalizedPoints
        .filter((point) => point.canWrite && point.writeTag)
        .map((point) => point.writeTag);
    const pointCatalog = normalizedPoints.map((point) => ({
        class: point.pointClass,
        canRead: point.canRead,
        readTag: point.readTag,
        canWrite: point.canWrite,
        writeTag: point.writeTag,
    }));
    if (form.value.connector_type === 'mock') {
        return {
            points: Object.fromEntries(normalizedPoints
                .filter((point) => point.canRead && point.readTag)
                .map((point) => [point.readTag, parseMockValue(point.mockValue)])),
            pointCatalog,
            readTags,
            writeTags,
        };
    }
    return {
        host: form.value.host,
        port: Number(form.value.port),
        db: Number(form.value.db),
        keyPrefix: form.value.keyPrefix,
        pointCatalog,
        readTags,
        writeTags,
    };
}
function parseMockValue(value) {
    if (value === '') {
        return '';
    }
    const numeric = Number(value);
    return Number.isNaN(numeric) ? value : numeric;
}
async function submit() {
    saving.value = true;
    error.value = '';
    try {
        await saveDataSource({
            name: form.value.name,
            connector_type: form.value.connector_type,
            config: buildConfig(),
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
async function remove(source) {
    if (!window.confirm(`删除数据源 ${source.name}？`)) {
        return;
    }
    error.value = '';
    try {
        await deleteDataSource(source.id);
        await loadDataSources();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '数据源删除失败';
    }
}
function pointCatalog(source) {
    const configured = source.config.pointCatalog ?? source.config.point_catalog;
    return Array.isArray(configured) ? configured.filter(isRecord) : [];
}
function pointClass(point) {
    return point.class || point.pointClass || '未分类';
}
function readTag(point) {
    return point.readTag || point.read_tag || '';
}
function writeTag(point) {
    return point.writeTag || point.write_tag || '';
}
function canRead(point) {
    return booleanField(point.canRead, point.can_read, Boolean(readTag(point)));
}
function canWrite(point) {
    return booleanField(point.canWrite, point.can_write, Boolean(writeTag(point)));
}
function booleanField(camel, snake, fallback) {
    if (typeof camel === 'boolean') {
        return camel;
    }
    if (typeof snake === 'boolean') {
        return snake;
    }
    return fallback;
}
function stringify(value) {
    return JSON.stringify(value, null, 2);
}
function isRecord(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
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
if (__VLS_ctx.form.connector_type === 'redis') {
    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
    (__VLS_ctx.form.host);
    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        type: "number",
    });
    (__VLS_ctx.form.port);
    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        type: "number",
    });
    (__VLS_ctx.form.db);
    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({});
    (__VLS_ctx.form.keyPrefix);
}
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "wide-field" },
});
/** @type {__VLS_StyleScopedClasses['wide-field']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "section-title" },
});
/** @type {__VLS_StyleScopedClasses['section-title']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
    ...{ onClick: (__VLS_ctx.addPoint) },
    type: "button",
    ...{ class: "secondary-button" },
});
/** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
    ...{ class: "point-grid point-grid-head" },
    ...{ class: ({ 'point-grid-mock': __VLS_ctx.form.connector_type === 'mock' }) },
});
/** @type {__VLS_StyleScopedClasses['point-grid']} */ ;
/** @type {__VLS_StyleScopedClasses['point-grid-head']} */ ;
/** @type {__VLS_StyleScopedClasses['point-grid-mock']} */ ;
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
if (__VLS_ctx.form.connector_type === 'mock') {
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
}
__VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
for (const [point, index] of __VLS_vFor((__VLS_ctx.points))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        key: (index),
        ...{ class: "point-grid" },
        ...{ class: ({ 'point-grid-mock': __VLS_ctx.form.connector_type === 'mock' }) },
    });
    /** @type {__VLS_StyleScopedClasses['point-grid']} */ ;
    /** @type {__VLS_StyleScopedClasses['point-grid-mock']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        placeholder: "如 DCS、RTO、pressure",
    });
    (point.pointClass);
    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
        ...{ class: "inline-check" },
    });
    /** @type {__VLS_StyleScopedClasses['inline-check']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        ...{ onChange: (...[$event]) => {
                __VLS_ctx.disableRead(point);
                // @ts-ignore
                [loadDataSources, loading, loading, error, error, submit, form, form, form, form, form, form, form, form, form, form, form, form, addPoint, points, disableRead,];
            } },
        type: "checkbox",
    });
    (point.readEnabled);
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        disabled: (!point.readEnabled),
        placeholder: "如 sthb:DCS_AO_RTO_014_AI",
    });
    (point.readTag);
    __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
        ...{ class: "inline-check" },
    });
    /** @type {__VLS_StyleScopedClasses['inline-check']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        ...{ onChange: (...[$event]) => {
                __VLS_ctx.disableWrite(point);
                // @ts-ignore
                [disableWrite,];
            } },
        type: "checkbox",
    });
    (point.writeEnabled);
    __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
        disabled: (!point.writeEnabled),
        placeholder: "如 sthb:DCS_AO_RTO_014_AO",
    });
    (point.writeTag);
    if (__VLS_ctx.form.connector_type === 'mock') {
        __VLS_asFunctionalElement1(__VLS_intrinsics.input)({
            disabled: (!point.readEnabled),
            placeholder: "如 21",
        });
        (point.mockValue);
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.removePoint(index);
                // @ts-ignore
                [form, removePoint,];
            } },
        type: "button",
        ...{ class: "danger-button" },
    });
    /** @type {__VLS_StyleScopedClasses['danger-button']} */ ;
    // @ts-ignore
    [];
}
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
    (source.read_enabled ? '数据源可读取' : '数据源不可读取');
    (source.write_enabled ? '数据源可回写' : '数据源不可回写');
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "package-meta" },
    });
    /** @type {__VLS_StyleScopedClasses['package-meta']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (source.status);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "row-actions" },
    });
    /** @type {__VLS_StyleScopedClasses['row-actions']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.remove(source);
                // @ts-ignore
                [saving, saving, dataSources, remove,];
            } },
        type: "button",
        ...{ class: "danger-button" },
    });
    /** @type {__VLS_StyleScopedClasses['danger-button']} */ ;
    if (__VLS_ctx.pointCatalog(source).length > 0) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "point-list" },
        });
        /** @type {__VLS_StyleScopedClasses['point-list']} */ ;
        for (const [point, index] of __VLS_vFor((__VLS_ctx.pointCatalog(source)))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                key: (index),
                ...{ class: "point-summary" },
            });
            /** @type {__VLS_StyleScopedClasses['point-summary']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
            (__VLS_ctx.pointClass(point));
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (__VLS_ctx.canRead(point) ? `读：${__VLS_ctx.readTag(point) || '未填'}` : '不可读');
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (__VLS_ctx.canWrite(point) ? `写：${__VLS_ctx.writeTag(point) || '未填'}` : '不可写');
            // @ts-ignore
            [pointCatalog, pointCatalog, pointClass, canRead, readTag, canWrite, writeTag,];
        }
    }
    __VLS_asFunctionalElement1(__VLS_intrinsics.pre, __VLS_intrinsics.pre)({});
    (__VLS_ctx.stringify(source.config));
    // @ts-ignore
    [stringify,];
}
// @ts-ignore
[];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
