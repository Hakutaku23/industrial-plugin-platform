/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/template-helpers.d.ts" />
/// <reference types="E:/深科先创/工作/广西深投/platform/frontend/node_modules/@vue/language-core/types/props-fallback.d.ts" />
import { onMounted, ref } from 'vue';
import { listPackages, listPackageVersions, runPackageVersion, } from '../api/packages';
const packages = ref([]);
const versions = ref({});
const loading = ref(false);
const loadingVersions = ref('');
const runningVersion = ref('');
const error = ref('');
const runInputs = ref({});
const runResults = ref({});
async function loadPackages() {
    loading.value = true;
    error.value = '';
    try {
        packages.value = await listPackages();
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '插件包列表加载失败';
    }
    finally {
        loading.value = false;
    }
}
async function toggleVersions(packageName) {
    if (versions.value[packageName]) {
        delete versions.value[packageName];
        versions.value = { ...versions.value };
        return;
    }
    loadingVersions.value = packageName;
    error.value = '';
    try {
        const loadedVersions = await listPackageVersions(packageName);
        versions.value = {
            ...versions.value,
            [packageName]: loadedVersions,
        };
        for (const version of loadedVersions) {
            runInputs.value[version.id] = runInputs.value[version.id] ?? '{}';
        }
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '插件版本加载失败';
    }
    finally {
        loadingVersions.value = '';
    }
}
async function runVersion(packageName, version) {
    runningVersion.value = `${packageName}@${version.version}`;
    error.value = '';
    try {
        const parsedInputs = JSON.parse(runInputs.value[version.id] || '{}');
        if (!parsedInputs || Array.isArray(parsedInputs) || typeof parsedInputs !== 'object') {
            throw new Error('输入 JSON 必须是对象');
        }
        const result = await runPackageVersion(packageName, version.version, parsedInputs);
        runResults.value = {
            ...runResults.value,
            [version.id]: result,
        };
    }
    catch (err) {
        error.value = err instanceof Error ? err.message : '插件执行失败';
    }
    finally {
        runningVersion.value = '';
    }
}
function formatJson(value) {
    return JSON.stringify(value, null, 2);
}
onMounted(loadPackages);
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
    ...{ onClick: (__VLS_ctx.loadPackages) },
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
if (__VLS_ctx.loading) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({
        ...{ class: "muted" },
    });
    /** @type {__VLS_StyleScopedClasses['muted']} */ ;
}
if (!__VLS_ctx.loading && __VLS_ctx.packages.length === 0) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "empty-state" },
    });
    /** @type {__VLS_StyleScopedClasses['empty-state']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.h3, __VLS_intrinsics.h3)({});
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
}
for (const [item] of __VLS_vFor((__VLS_ctx.packages))) {
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        key: (item.id),
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
    (item.name);
    __VLS_asFunctionalElement1(__VLS_intrinsics.h3, __VLS_intrinsics.h3)({});
    (item.display_name);
    __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
    (item.description);
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "package-meta" },
    });
    /** @type {__VLS_StyleScopedClasses['package-meta']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (item.status);
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (item.version_count);
    __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
    (item.latest_version ?? '无');
    __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
        ...{ class: "row-actions" },
    });
    /** @type {__VLS_StyleScopedClasses['row-actions']} */ ;
    __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.toggleVersions(item.name);
                // @ts-ignore
                [loadPackages, loading, loading, loading, loading, error, error, packages, packages, toggleVersions,];
            } },
        type: "button",
        ...{ class: "secondary-button" },
        disabled: (__VLS_ctx.loadingVersions === item.name),
    });
    /** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
    (__VLS_ctx.versions[item.name] ? '收起版本' : __VLS_ctx.loadingVersions === item.name ? '加载中' : '查看版本');
    if (__VLS_ctx.versions[item.name]) {
        __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
            ...{ class: "version-list" },
        });
        /** @type {__VLS_StyleScopedClasses['version-list']} */ ;
        for (const [version] of __VLS_vFor((__VLS_ctx.versions[item.name]))) {
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({
                key: (version.id),
                ...{ class: "version-row" },
            });
            /** @type {__VLS_StyleScopedClasses['version-row']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.div, __VLS_intrinsics.div)({});
            __VLS_asFunctionalElement1(__VLS_intrinsics.strong, __VLS_intrinsics.strong)({});
            (version.version);
            __VLS_asFunctionalElement1(__VLS_intrinsics.span, __VLS_intrinsics.span)({});
            (version.status);
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
            (version.digest);
            __VLS_asFunctionalElement1(__VLS_intrinsics.p, __VLS_intrinsics.p)({});
            (version.package_path);
            __VLS_asFunctionalElement1(__VLS_intrinsics.label, __VLS_intrinsics.label)({
                ...{ class: "json-input" },
            });
            /** @type {__VLS_StyleScopedClasses['json-input']} */ ;
            __VLS_asFunctionalElement1(__VLS_intrinsics.textarea, __VLS_intrinsics.textarea)({
                value: (__VLS_ctx.runInputs[version.id]),
                rows: "4",
                spellcheck: "false",
            });
            __VLS_asFunctionalElement1(__VLS_intrinsics.button, __VLS_intrinsics.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.versions[item.name]))
                            return;
                        __VLS_ctx.runVersion(item.name, version);
                        // @ts-ignore
                        [loadingVersions, loadingVersions, versions, versions, versions, runInputs, runVersion,];
                    } },
                type: "button",
                ...{ class: "secondary-button" },
                disabled: (__VLS_ctx.runningVersion === `${item.name}@${version.version}`),
            });
            /** @type {__VLS_StyleScopedClasses['secondary-button']} */ ;
            (__VLS_ctx.runningVersion === `${item.name}@${version.version}` ? '执行中' : 'Dry-run 执行');
            if (__VLS_ctx.runResults[version.id]) {
                __VLS_asFunctionalElement1(__VLS_intrinsics.pre, __VLS_intrinsics.pre)({});
                (__VLS_ctx.formatJson(__VLS_ctx.runResults[version.id]));
            }
            // @ts-ignore
            [runningVersion, runningVersion, runResults, runResults, formatJson,];
        }
    }
    // @ts-ignore
    [];
}
// @ts-ignore
[];
const __VLS_export = (await import('vue')).defineComponent({});
export default {};
