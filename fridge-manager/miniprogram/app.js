// app.js
const DEVTOOLS_API_BASE_URL = 'http://127.0.0.1:8000/api/v1'
const LOCALHOST_API_BASE_URL = 'http://localhost:8000/api/v1'
const LAN_API_BASE_URL = 'http://192.168.1.250:8000/api/v1'

App({
  onLaunch() {
    // 小程序启动时执行
    console.log('🧊 冰箱管家启动')
    
    // 检查更新
    if (wx.canIUse('getUpdateManager')) {
      const updateManager = wx.getUpdateManager()
      updateManager.onCheckForUpdate(function (res) {
        if (res.hasUpdate) {
          updateManager.onUpdateReady(function () {
            wx.showModal({
              title: '更新提示',
              content: '新版本已经准备好，是否重启应用？',
              success(res) {
                if (res.confirm) {
                  updateManager.applyUpdate()
                }
              }
            })
          })
        }
      })
    }
  },

  clearPendingNavigation() {
    if (this.pendingNavigationTimer) {
      clearTimeout(this.pendingNavigationTimer)
      this.pendingNavigationTimer = null
    }
  },

  scheduleNavigation(callback, delay = 0) {
    this.clearPendingNavigation()
    this.pendingNavigationTimer = setTimeout(() => {
      this.pendingNavigationTimer = null
      if (typeof callback === 'function') {
        callback()
      }
    }, delay)
  },

  markFoodListDirty() {
    this.globalData.foodListDirty = true
  },

  consumeFoodListDirty() {
    const dirty = !!this.globalData.foodListDirty
    this.globalData.foodListDirty = false
    return dirty
  },
  
  globalData: {
    // API 基础地址（开发时改为你的后端地址）
    API_BASE_URL: wx.getSystemInfoSync().platform === 'devtools'
      ? DEVTOOLS_API_BASE_URL
      : LAN_API_BASE_URL,
    API_BASE_URL_FALLBACKS: wx.getSystemInfoSync().platform === 'devtools'
      ? [LOCALHOST_API_BASE_URL, LAN_API_BASE_URL]
      : [DEVTOOLS_API_BASE_URL, LOCALHOST_API_BASE_URL],
    
    // 用户信息
    userInfo: null,
    foodListDirty: false,
    
    // 食物类别映射
    foodCategories: {
      '蔬菜': { icon: '🥬', color: '#34C759' },
      '水果': { icon: '🍎', color: '#FF9500' },
      '肉类': { icon: '🥩', color: '#FF3B30' },
      '海鲜': { icon: '🐟', color: '#5AC8FA' },
      '蛋类': { icon: '🥚', color: '#FFCC00' },
      '乳制品': { icon: '🥛', color: '#FFFFFF' },
      '豆制品': { icon: '🧊', color: '#AF52DE' },
      '主食': { icon: '🍚', color: '#FF9500' },
      '熟食': { icon: '🍲', color: '#A2845E' },
      '剩菜': { icon: '🥡', color: '#64D2FF' },
      '其他': { icon: '📦', color: '#8E8E93' },
    },
    
    // 状态配置
    statusConfig: {
      'fresh': { text: '新鲜', color: '#34C759', bg: '#E8F5E9' },
      'warning': { text: '临期', color: '#FF9500', bg: '#FFF3E0' },
      'expired': { text: '过期', color: '#FF3B30', bg: '#FFEBEE' },
    },
  },
  
  /**
   * 格式化日期
   */
  formatDate(dateStr) {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now - date
    
    // 今天
    if (diff < 24 * 60 * 60 * 1000 && date.getDate() === now.getDate()) {
      return '今天'
    }
    
    // 昨天
    if (diff < 48 * 60 * 60 * 1000) {
      return '昨天'
    }
    
    // 其他日期
    const month = date.getMonth() + 1
    const day = date.getDate()
    return `${month}月${day}日`
  },
  
  /**
   * 计算剩余天数
   */
  calcDaysLeft(expiryDate) {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const expiry = new Date(expiryDate)
    expiry.setHours(0, 0, 0, 0)
    
    const diff = expiry - today
    const days = Math.ceil(diff / (24 * 60 * 60 * 1000))
    
    if (days < 0) {
      return { text: `过期${Math.abs(days)}天`, type: 'expired' }
    } else if (days === 0) {
      return { text: '今天过期', type: 'warning' }
    } else if (days === 1) {
      return { text: '明天过期', type: 'warning' }
    } else if (days <= 3) {
      return { text: `${days}天后过期`, type: 'warning' }
    } else {
      return { text: `${days}天后过期`, type: 'fresh' }
    }
  },
})
