import { createRouter, createWebHistory } from 'vue-router';
import DataSources from '../views/DataSources.vue';
import Instances from '../views/Instances.vue';
import PluginList from '../views/PluginList.vue';
import PluginUpload from '../views/PluginUpload.vue';
import RunList from '../views/RunList.vue';
export const router = createRouter({
    history: createWebHistory(),
    routes: [
        {
            path: '/',
            name: 'plugin-upload',
            component: PluginUpload,
        },
        {
            path: '/packages',
            name: 'plugin-list',
            component: PluginList,
        },
        {
            path: '/data-sources',
            name: 'data-sources',
            component: DataSources,
        },
        {
            path: '/instances',
            name: 'instances',
            component: Instances,
        },
        {
            path: '/runs',
            name: 'run-list',
            component: RunList,
        },
    ],
});
