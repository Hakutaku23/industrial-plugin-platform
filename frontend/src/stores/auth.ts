import { defineStore } from 'pinia'
import { ApiError } from '../api/client'
import { getMe, getSecurityStatus, login, logout, type AuthMeResponse } from '../api/auth'

interface UserInfo {
  id: number | null
  username: string
  display_name: string
  email: string | null
  roles: string[]
  permissions: string[]
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    loaded: false,
    securityEnabled: false,
    authenticated: false,
    authMode: 'local-session',
    user: null as UserInfo | null,
    loginError: '',
  }),
  getters: {
    can: (state) => (permission: string) => !state.securityEnabled || Boolean(state.user?.permissions.includes(permission)),
    isAdmin: (state) => state.user?.roles.includes('admin') ?? false,
  },
  actions: {
    async bootstrap() {
      if (this.loaded) return
      const status = await getSecurityStatus()
      this.securityEnabled = status.enabled
      this.authMode = status.auth_mode
      if (!status.enabled) {
        this.authenticated = true
        this.user = {
          id: null,
          username: 'local-dev',
          display_name: 'Local Development',
          email: null,
          roles: ['admin'],
          permissions: [],
        }
        this.loaded = true
        return
      }
      await this.refreshMe()
      this.loaded = true
    },
    async refreshMe() {
      const payload = await getMe()
      this.securityEnabled = payload.security_enabled
      this.authenticated = payload.authenticated
      this.user = payload.user
    },
    async signIn(username: string, password: string) {
      this.loginError = ''
      try {
        await login(username, password)
        await this.refreshMe()
      } catch (error) {
        if (error instanceof ApiError) {
          this.loginError = error.message
        } else {
          this.loginError = '登录失败'
        }
        throw error
      }
    },
    async signOut() {
      await logout()
      if (this.securityEnabled) {
        this.authenticated = false
        this.user = null
      }
    },
  },
})
