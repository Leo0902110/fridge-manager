// utils/api.js - API 调用封装

const app = getApp()

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

/**
 * 基础请求封装
 */
function request(url, options = {}) {
  const fullUrl = `${app.globalData.API_BASE_URL}${url}`
  const data = cleanData(options.data || {})
  console.log('API request:', fullUrl, data)

  return new Promise((resolve, reject) => {
    wx.request({
      url: fullUrl,
      method: options.method || 'GET',
      data,
      header: {
        'Content-Type': 'application/json',
        ...options.header,
      },
      timeout: 10000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject({
            code: res.statusCode,
            message: typeof res.data?.detail === 'string' ? res.data.detail : (res.data?.message || '请求失败'),
          })
        }
      },
      fail: (err) => {
        reject({
          code: 500,
          message: `${err.errMsg || '网络错误'}：${fullUrl}`,
        })
      },
    })
  })
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
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: `${app.globalData.API_BASE_URL}/foods/upload-image`,
        filePath: imagePath,
        name: 'image',
        success: (res) => {
          try {
            const data = JSON.parse(res.data)
            if (data.success) {
              resolve(data)
            } else {
              reject({ message: data.message || '图片上传失败' })
            }
          } catch (e) {
            reject({ message: '图片上传结果解析失败' })
          }
        },
        fail: (err) => {
          reject({ message: err.errMsg || '图片上传失败' })
        },
      })
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
  
  // 获取概览统计
  overview() {
    return request('/foods/stats/overview')
  },
  
  // 获取保质期参考
  getShelfLifeReference(foodName) {
    return request('/foods/reference/shelf-life', {
      data: { food_name: foodName },
    })
  },
}

/**
 * AI 识别 API
 */
const recognitionAPI = {
  // 图片识别
  recognizeImage(imagePath) {
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: `${app.globalData.API_BASE_URL}/recognition/image`,
        filePath: imagePath,
        name: 'image',
        success: (res) => {
          try {
            const data = JSON.parse(res.data)
            if (data.success) {
              resolve(data)
            } else {
              reject({ message: data.message || '识别失败' })
            }
          } catch (e) {
            reject({ message: '解析失败' })
          }
        },
        fail: (err) => {
          reject({ message: err.errMsg || '上传失败' })
        },
      })
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

module.exports = {
  food: foodAPI,
  recognition: recognitionAPI,
  reminder: reminderAPI,
  foodAPI,
  recognitionAPI,
  reminderAPI,
}
