import axios from 'axios'
import type { ApiResponse } from './types'

const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ━━━ 响应拦截器 ━━━
client.interceptors.response.use(
  (response) => {
    const data = response.data as ApiResponse<unknown>
    if (data.success === false) {
      return Promise.reject(new Error(data.message || '请求失败'))
    }
    return response
  },
  (error) => {
    const message = error.response?.data?.message || error.message || '网络错误'
    console.error('[API Error]', message)
    return Promise.reject(new Error(message))
  },
)

export default client
