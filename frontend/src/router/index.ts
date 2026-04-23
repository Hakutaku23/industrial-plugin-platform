import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { pinia } from '../stores/pinia'
import AdminUsers from '../views/AdminUsers.vue'
import DataSources from '../views/DataSources.vue'
import Instances from '../views/Instances.vue'
import LicenseCenter from '../views/LicenseCenter.vue'
import Login from '../views/Login.vue'
import PluginList from '../views/PluginList.vue'
import PluginUpload from '../views/PluginUpload.vue'
import RunList from '../views/RunList.vue'
import SystemObservability from '../views/SystemObservability.vue'
import UserProfile from '../views/UserProfile.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: Login, meta: { public: true } },
    { path: '/', name: 'plugin-upload', component: PluginUpload, meta: { permission: 'package.read' } },
    { path: '/packages', name: 'plugin-list', component: PluginList, meta: { permission: 'package.read' } },
    { path: '/data-sources', name: 'data-sources', component: DataSources, meta: { permission: 'datasource.read' } },
    { path: '/instances', name: 'instances', component: Instances, meta: { permission: 'instance.read' } },
    { path: '/runs', name: 'run-list', component: RunList, meta: { permission: 'run.read' } },
    { path: '/system/observability', name: 'system-observability', component: SystemObservability, meta: { permission: 'system.read' } },
    { path: '/license', name: 'license-center', component: LicenseCenter, meta: { permission: 'system.read' } },
    { path: '/admin/users', name: 'admin-users', component: AdminUsers, meta: { permission: 'user.read' } },
    { path: '/profile', name: 'profile', component: UserProfile },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore(pinia)
  await auth.bootstrap()

  if (to.meta.public) {
    if (to.path === '/login' && (!auth.securityEnabled || auth.authenticated)) {
      const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
      return redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/'
    }
    return true
  }

  if (auth.securityEnabled && !auth.authenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  const requiredPermission = typeof to.meta.permission === 'string' ? to.meta.permission : ''
  if (requiredPermission && !auth.can(requiredPermission)) {
    return '/'
  }

  return true
})
