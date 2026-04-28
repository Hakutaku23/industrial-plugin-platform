import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { pinia } from '../stores/pinia'
import AdminUsers from '../views/AdminUsers.vue'
import DataSources from '../views/DataSources.vue'
import HomeCenter from '../views/HomeCenter.vue'
import Instances from '../views/Instances.vue'
import InstanceModelBinding from '../views/InstanceModelBinding.vue'
import LicenseCenter from '../views/LicenseCenter.vue'
import Login from '../views/Login.vue'
import ModelRegistry from '../views/ModelRegistry.vue'
import ModelUpdateJobs from '../views/ModelUpdateJobs.vue'
import PluginList from '../views/PluginList.vue'
import PluginUpload from '../views/PluginUpload.vue'
import RunList from '../views/RunList.vue'
import RuntimeDiagnostics from '../views/RuntimeDiagnostics.vue'
import SystemSettings from '../views/SystemSettings.vue'
import TemplateCenter from '../views/TemplateCenter.vue'
import UserProfile from '../views/UserProfile.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: Login, meta: { public: true } },
    { path: '/', name: 'home-center', component: HomeCenter, meta: { permission: 'package.read' } },
    { path: '/home', redirect: '/' },
    { path: '/packages/upload', name: 'plugin-upload', component: PluginUpload, meta: { permission: 'package.read' } },
    { path: '/templates', name: 'template-center', component: TemplateCenter, meta: { permission: 'package.read' } },
    { path: '/packages', name: 'plugin-list', component: PluginList, meta: { permission: 'package.read' } },
    { path: '/models', name: 'model-registry', component: ModelRegistry, meta: { permission: 'package.read' } },
    { path: '/model-updates', name: 'model-update-jobs', component: ModelUpdateJobs, meta: { permission: 'instance.read' } },
    { path: '/data-sources', name: 'data-sources', component: DataSources, meta: { permission: 'datasource.read' } },
    { path: '/instances/model-binding', name: 'instance-model-binding', component: InstanceModelBinding, meta: { permission: 'instance.read' } },
    { path: '/instances', name: 'instances', component: Instances, meta: { permission: 'instance.read' } },
    { path: '/runs', name: 'run-list', component: RunList, meta: { permission: 'run.read' } },
    { path: '/system/settings', name: 'system-settings', component: SystemSettings, meta: { permission: 'system.read' } },
    { path: '/license', name: 'license-center', component: LicenseCenter, meta: { permission: 'system.read' } },
    { path: '/admin/users', name: 'admin-users', component: AdminUsers, meta: { permission: 'user.read' } },
    { path: '/profile', name: 'profile', component: UserProfile },
    { path: '/runtime-diagnostics', name: 'runtime-diagnostics', component: RuntimeDiagnostics, meta: { permission: 'system.read' } },
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
