export async function uploadPackage(file) {
    const response = await fetch(`/api/v1/packages?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/octet-stream',
        },
        body: await file.arrayBuffer(),
    });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || '插件包上传失败');
    }
    return response.json();
}
export async function listPackages() {
    const response = await fetch('/api/v1/packages');
    if (!response.ok) {
        throw new Error(await response.text() || '插件包列表加载失败');
    }
    const payload = await response.json();
    return payload.items;
}
export async function listPackageVersions(packageName) {
    const response = await fetch(`/api/v1/packages/${encodeURIComponent(packageName)}/versions`);
    if (!response.ok) {
        throw new Error(await response.text() || '插件版本加载失败');
    }
    const payload = await response.json();
    return payload.items;
}
export async function runPackageVersion(packageName, version, inputs, config = {}) {
    const response = await fetch(`/api/v1/packages/${encodeURIComponent(packageName)}/versions/${encodeURIComponent(version)}/runs`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ inputs, config }),
    });
    if (!response.ok) {
        throw new Error(await response.text() || '插件执行失败');
    }
    return response.json();
}
export async function listRuns(packageName, instanceId) {
    const params = new URLSearchParams();
    if (packageName) {
        params.set('package_name', packageName);
    }
    if (instanceId !== undefined) {
        params.set('instance_id', String(instanceId));
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await fetch(`/api/v1/runs${query}`);
    if (!response.ok) {
        throw new Error(await response.text() || '运行记录加载失败');
    }
    const payload = await response.json();
    return payload.items;
}
export async function listDataSources() {
    const response = await fetch('/api/v1/data-sources');
    if (!response.ok) {
        throw new Error(await response.text() || '数据源列表加载失败');
    }
    const payload = await response.json();
    return payload.items;
}
export async function saveDataSource(payload) {
    const response = await fetch('/api/v1/data-sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw new Error(await response.text() || '数据源保存失败');
    }
    return response.json();
}
export async function deleteDataSource(dataSourceId) {
    const response = await fetch(`/api/v1/data-sources/${dataSourceId}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        throw new Error(await response.text() || '数据源删除失败');
    }
}
export async function listInstances() {
    const response = await fetch('/api/v1/instances');
    if (!response.ok) {
        throw new Error(await response.text() || '实例列表加载失败');
    }
    const payload = await response.json();
    return payload.items;
}
export async function saveInstance(payload) {
    const endpoint = payload.id ? `/api/v1/instances/${payload.id}` : '/api/v1/instances';
    const response = await fetch(endpoint, {
        method: payload.id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw new Error(await response.text() || '实例保存失败');
    }
    return response.json();
}
export async function updateInstanceSchedule(instanceId, payload) {
    const response = await fetch(`/api/v1/instances/${instanceId}/schedule`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw new Error(await response.text() || '实例定时状态更新失败');
    }
    return response.json();
}
export async function deleteInstance(instanceId) {
    const response = await fetch(`/api/v1/instances/${instanceId}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        throw new Error(await response.text() || '实例删除失败');
    }
}
export async function runInstance(instanceId) {
    const response = await fetch(`/api/v1/instances/${instanceId}/runs`, {
        method: 'POST',
    });
    if (!response.ok) {
        throw new Error(await response.text() || '实例运行失败');
    }
    return response.json();
}
