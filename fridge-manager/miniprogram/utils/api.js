// utils/api.js - API 调用封装

const app = getApp()
const DEFAULT_TIMEOUT = 10000
const UPLOAD_TIMEOUT = 20000
const RECOGNITION_TIMEOUT = 60000
const AUTH_TOKEN_KEY = 'FRIDGE_AUTH_TOKEN'

function cleanData(data = {}) {
  const cleaned = {}
  Object.keys(data).forEach((key) => {
    const value = data[key]
    if (value !== null && value !== undefined && value !== '') {
      cleaned[key] = value
    }
  })
  return cleaned
}

function getApiBaseUrls() {
  const urls = [
    app.globalData.API_BASE_URL,
    ...(app.globalData.API_BASE_URL_FALLBACKS || []),
  ]
  return urls.filter((url, index) => url && urls.indexOf(url) === index)
}

function isPlaceholderApiUrl(url) {
  return typeof url === 'string' && /your-domain\.com|example\.com/.test(url)
}

function rejectUnconfiguredApi(reject) {
  const baseUrls = getApiBaseUrls()
  if (!baseUrls.length) {
    reject({ code: 500, message: '后端地址未配置' })
    return true
  }
  if (baseUrls.every(isPlaceholderApiUrl)) {
    reject({ code: 500, message: '正式后端域名还没配置，请先修改 miniprogram/app.js 的 PRODUCTION_API_BASE_URL' })
    return true
  }
  return false
}

function getStoredAuthToken() {
  if (app.globalData.authToken) {
    return app.globalData.authToken
  }
  const token = wx.getStorageSync(AUTH_TOKEN_KEY) || ''
  app.globalData.authToken = token
  return token
}

function setAuthToken(token) {
  app.globalData.authToken = token || ''
  if (token) {
    wx.setStorageSync(AUTH_TOKEN_KEY, token)
  } else {
    wx.removeStorageSync(AUTH_TOKEN_KEY)
  }
}

function wxLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        if (res.code) {
          resolve(res.code)
          return
        }
        reject({ message: '微信登录失败' })
      },
      fail(err) {
        reject({ message: err.errMsg || '微信登录失败' })
      },
    })
  })
}

function loginWithCode(code) {
  const baseUrls = getApiBaseUrls().filter(baseUrl => !isPlaceholderApiUrl(baseUrl))

  return new Promise((resolve, reject) => {
    if (rejectUnconfiguredApi(reject)) {
      return
    }
    if (!baseUrls.length) {
      reject({ code: 500, message: '后端地址未配置' })
      return
    }

    const tryLogin = (index = 0) => {
      const baseUrl = baseUrls[index]
      const fullUrl = `${baseUrl}/auth/login`
      wx.request({
        url: fullUrl,
        method: 'POST',
        data: { code },
        header: { 'Content-Type': 'application/json' },
        timeout: DEFAULT_TIMEOUT,
        success(res) {
          const data = res.data || {}
          if (res.statusCode >= 200 && res.statusCode < 300 && data.success && data.data && data.data.token) {
            rememberSuccessfulBaseUrl(baseUrl)
            setAuthToken(data.data.token)
            resolve(data.data.token)
            return
          }
          reject({ code: res.statusCode, message: normalizeErrorMessage(data, '登录失败') })
        },
        fail(err) {
          if (index < baseUrls.length - 1 && shouldRetryNetworkError(err)) {
            tryLogin(index + 1)
            return
          }
          reject({ code: 500, message: `${err.errMsg || '登录失败'}：${fullUrl}` })
        },
      })
    }

    tryLogin()
  })
}

function ensureAuthenticated() {
  const token = getStoredAuthToken()
  if (token) {
    return Promise.resolve(token)
  }

  if (app.globalData.loginPromise) {
    return app.globalData.loginPromise
  }

  const loginPromise = wxLogin().then(code => loginWithCode(code))
  app.globalData.loginPromise = loginPromise
  loginPromise.then(
    () => { app.globalData.loginPromise = null },
    () => { app.globalData.loginPromise = null },
  )
  return loginPromise
}

function rememberSuccessfulBaseUrl(baseUrl) {
  if (baseUrl && app.globalData.API_BASE_URL !== baseUrl) {
    app.globalData.API_BASE_URL = baseUrl
    console.log('API base switched:', baseUrl)
  }
}

function normalizeErrorMessage(data, fallback = '请求失败') {
  if (typeof data?.detail === 'string') {
    return data.detail
  }
  if (Array.isArray(data?.detail)) {
    return data.detail.map(item => item.msg || item.message || JSON.stringify(item)).join('；')
  }
  return data?.message || fallback
}

function shouldRetryNetworkError(err, options = {}) {
  const message = err.errMsg || ''
  if (message.includes('timeout') && options.retryOnTimeout === false) {
    return false
  }
  return true
}

/**
 * 基础请求封装
 */
function request(url, options = {}) {
  const baseUrls = getApiBaseUrls().filter(baseUrl => !isPlaceholderApiUrl(baseUrl))
  const data = cleanData(options.data || {})

  return ensureAuthenticated().then((authToken) => new Promise((resolve, reject) => {
    if (rejectUnconfiguredApi(reject)) {
      return
    }

    const tryRequest = (index = 0) => {
      const baseUrl = baseUrls[index]
      const fullUrl = `${baseUrl}${url}`
      console.log('API request:', fullUrl, data)

      wx.request({
        url: fullUrl,
        method: options.method || 'GET',
        data,
        header: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
          ...options.header,
        },
        timeout: options.timeout || DEFAULT_TIMEOUT,
        success: (res) => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            rememberSuccessfulBaseUrl(baseUrl)
            resolve(res.data)
          } else if (res.statusCode === 401) {
            setAuthToken('')
            reject({ code: 401, message: normalizeErrorMessage(res.data, '登录已过期，请重试') })
          } else {
            reject({
              code: res.statusCode,
              message: normalizeErrorMessage(res.data),
            })
          }
        },
        fail: (err) => {
          if (index < baseUrls.length - 1 && shouldRetryNetworkError(err, options)) {
            tryRequest(index + 1)
            return
          }
          reject({
            code: 500,
            message: `${err.errMsg || '网络错误'}：${fullUrl}`,
          })
        },
      })
    }

    tryRequest()
  }))
}

function uploadFileWithFallback(url, imagePath, options = {}) {
  const baseUrls = getApiBaseUrls().filter(baseUrl => !isPlaceholderApiUrl(baseUrl))
  return ensureAuthenticated().then((authToken) => new Promise((resolve, reject) => {
    if (rejectUnconfiguredApi(reject)) {
      return
    }

    const tryUpload = (index = 0) => {
      const baseUrl = baseUrls[index]
      const fullUrl = `${baseUrl}${url}`

      wx.uploadFile({
        url: fullUrl,
        filePath: imagePath,
        name: options.name || 'image',
        header: {
          Authorization: `Bearer ${authToken}`,
          ...options.header,
        },
        timeout: options.timeout || UPLOAD_TIMEOUT,
        success: (res) => {
          try {
            const data = JSON.parse(res.data)
            if (res.statusCode >= 200 && res.statusCode < 300 && data.success) {
              rememberSuccessfulBaseUrl(baseUrl)
              resolve(data)
            } else if (res.statusCode === 401) {
              setAuthToken('')
              reject({ message: normalizeErrorMessage(data, '登录已过期，请重试') })
            } else {
              reject({ message: normalizeErrorMessage(data, options.failMessage || '上传失败') })
            }
          } catch (e) {
            reject({ message: options.parseMessage || '返回结果解析失败' })
          }
        },
        fail: (err) => {
          if (index < baseUrls.length - 1 && shouldRetryNetworkError(err, options)) {
            tryUpload(index + 1)
            return
          }
          reject({ message: `${err.errMsg || options.failMessage || '上传失败'}：${fullUrl}` })
        },
      })
    }

    tryUpload()
  }))
}

/**
 * 食物管理 API
 */
const foodAPI = {
  // 获取食物列表
  list(params = {}) {
    return request('/foods', { data: params })
  },
  
  // 获取食物详情
  detail(id) {
    return request(`/foods/${id}`)
  },
  
  // 添加食物
  create(data) {
    return request('/foods', {
      method: 'POST',
      data,
    })
  },

  // 上传食物裁剪图
  uploadImage(imagePath) {
    return uploadFileWithFallback('/foods/upload-image', imagePath, {
      timeout: UPLOAD_TIMEOUT,
      failMessage: '图片上传失败',
      parseMessage: '图片上传结果解析失败',
    })
  },
  
  // 更新食物
  update(id, data) {
    return request(`/foods/${id}`, {
      method: 'PUT',
      data,
    })
  },
  
  // 删除食物
  delete(id) {
    return request(`/foods/${id}`, {
      method: 'DELETE',
    })
  },

  // 标记吃完/丢弃，并保留统计记录
  complete(id, action = 'eat') {
    return request(`/foods/${id}/complete`, {
      method: 'POST',
      data: { action },
    })
  },

  // 撤销完成记录
  deleteEvent(eventId) {
    return request(`/foods/events/${eventId}`, {
      method: 'DELETE',
    })
  },
  
  // 获取概览统计
  overview() {
    return request('/foods/stats/overview')
  },
  
  // 获取保质期参考
  getShelfLifeReference(foodName, category) {
    return request('/foods/reference/shelf-life', {
      data: { food_name: foodName, category },
    })
  },
}

/**
 * AI 识别 API
 */
const recognitionAPI = {
  // 图片识别
  recognizeImage(imagePath) {
    return uploadFileWithFallback('/recognition/image', imagePath, {
      timeout: RECOGNITION_TIMEOUT,
      retryOnTimeout: false,
      failMessage: '识别失败',
      parseMessage: '识别结果解析失败',
    })
  },
  
  // 名称查询
  recognizeByName(name) {
    return request('/recognition/name', {
      method: 'POST',
      data: { name },
    })
  },
  
  // 获取食物类别
  getCategories() {
    return request('/recognition/categories')
  },
}

/**
 * 提醒 API
 */
const reminderAPI = {
  // 获取待发送提醒
  getPending() {
    return request('/reminders/pending')
  },
  
  // 检查临期食物
  checkExpiry() {
    return request('/reminders/check-expiry', {
      method: 'POST',
    })
  },
  
  // 获取历史提醒
  getHistory(limit = 50) {
    return request(`/reminders/history?limit=${limit}`)
  },
}

const authAPI = {
  login() {
    return ensureAuthenticated().then(token => ({ success: true, data: { token } }))
  },

  me() {
    return request('/auth/me')
  },

  logout() {
    const token = getStoredAuthToken()
    setAuthToken('')
    if (!token) {
      return Promise.resolve({ success: true })
    }

    const baseUrls = getApiBaseUrls().filter(baseUrl => !isPlaceholderApiUrl(baseUrl))
    return new Promise((resolve) => {
      if (!baseUrls.length) {
        resolve({ success: true })
        return
      }
      wx.request({
        url: `${baseUrls[0]}/auth/logout`,
        method: 'POST',
        header: { Authorization: `Bearer ${token}` },
        timeout: DEFAULT_TIMEOUT,
        complete() {
          resolve({ success: true })
        },
      })
    })
  },
}

module.exports = {
  auth: authAPI,
  food: foodAPI,
  recognition: recognitionAPI,
  reminder: reminderAPI,
  authAPI,
  foodAPI,
  recognitionAPI,
  reminderAPI,
}
