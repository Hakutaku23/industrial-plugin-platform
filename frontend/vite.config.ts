import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import postCssPxToRem from 'postcss-pxtorem'
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  css: {
    postcss: {
      plugins: [
        postCssPxToRem({
          rootValue: 16, // 上面 App.vue 里设置的 baseFontSize
          propList: ['font', 'font-size', 'line-height', 'letter-spacing'], // 只转换字体相关。如果想全站(宽高边距)都跟着放大，填 ['*']
          minPixelValue: 2, // 小于2px不转换
          selectorBlackList: ['.norem'] // 过滤掉不需要转换的类名
        })
      ]
    }
  }
})