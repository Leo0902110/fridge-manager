// pages/index/index.js
const app = getApp()
const api = require('../../utils/api.js')

function getCountdownInfo(expiryDate) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const expiry = new Date(expiryDate)
  expiry.setHours(0, 0, 0, 0)

  const days = Math.ceil((expiry - today) / (24 * 60 * 60 * 1000))

  if (days < 0) {
    return {
      days,
      riskRank: 0,
      riskType: 'expired',
      countdownText: `已过期 ${Math.abs(days)} 天`,
      badgeText: '已过期',
    }
  }

  if (days === 0) {
    return {
      days,
      riskRank: 1,
      riskType: 'warning',
      countdownText: '今天到期',
      badgeText: '今天',
    }
  }

  if (days <= 3) {
    return {
      days,
      riskRank: 1,
      riskType: 'warning',
      countdownText: `${days} 天后到期`,
      badgeText: '即将过期',
    }
  }

  return {
    days,
    riskRank: 2,
    riskType: 'fresh',
    countdownText: `${days} 天后到期`,
    badgeText: '健康',
  }
}

Page({
  data: {
    stats: {
      total: 0,
      fresh_count: 0,
      warning_count: 0,
      expired_count: 0,
      warning_foods: [],
    },
    foodList: [],
    filter: 'all',
    loading: false,
    refreshing: false,
    initialized: false,
    lastUpdatedText: '正在同步',
  },

  onLoad() {
    this.updateTabBar()
  },

  onShow() {
    // 每次显示时刷新数据
    this.updateTabBar()
    this.loadData()
  },

  onPullDownRefresh() {
    this.loadData({ refresh: true }).then(() => {
      wx.stopPullDownRefresh()
    })
  },

  /**
   * 加载数据
   */
  async loadData(options = {}) {
    const { refresh = false } = options

    this.setData({
      loading: true,
      refreshing: refresh,
      lastUpdatedText: refresh ? '刷新中' : '正在同步',
    })
    wx.showNavigationBarLoading()
    
    try {
      // 加载概览统计
      const overviewRes = await api.food.overview()
      if (overviewRes.success) {
        this.setData({
          stats: overviewRes.data,
        })
      }
      
      // 加载食物列表
      const listParams = this.data.filter === 'warning' ? { status: 'warning' } : {}
      const listRes = await api.food.list(listParams)
      if (listRes.success) {
        const foodList = listRes.data
          .map((food) => {
            const countdown = getCountdownInfo(food.expiry_date)
            return {
              ...food,
              ...countdown,
            }
          })
          .sort((a, b) => {
            if (a.riskRank !== b.riskRank) {
              return a.riskRank - b.riskRank
            }
            return a.days - b.days
          })

        this.setData({
          foodList,
        })
      }

      this.setData({
        initialized: true,
        lastUpdatedText: `刚刚更新`,
      })
    } catch (err) {
      console.error('加载数据失败:', err)
      this.setData({
        initialized: true,
        lastUpdatedText: '更新失败',
      })
      wx.showToast({
        title: err.message || '加载失败',
        icon: 'none',
      })
    } finally {
      this.setData({ loading: false, refreshing: false })
      wx.hideNavigationBarLoading()
    }
  },

  /**
   * 设置筛选
   */
  setFilter(e) {
    const filter = e.currentTarget.dataset.filter
    this.setData({ filter })
    this.loadData({ refresh: false })
  },

  /**
   * 跳转到详情页
   */
  goToDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: `/pages/detail/detail?id=${id}`,
    })
  },

  /**
   * 跳转到添加页
   */
  goToAdd() {
    wx.switchTab({
      url: '/pages/add/add',
    })
  },

  /**
   * 获取类别图标
   */
  getCategoryIcon(category) {
    const categories = app.globalData.foodCategories
    return (categories[category] || categories['其他']).icon
  },

  /**
   * 格式化日期
   */
  formatDate(dateStr) {
    return app.formatDate(dateStr)
  },

  /**
   * 计算剩余天数
   */
  calcDaysLeft(expiryDate) {
    return app.calcDaysLeft(expiryDate)
  },

  /**
   * 计算剩余天数（用于临期提醒）
   */
  daysLeft(expiryDate) {
    const result = app.calcDaysLeft(expiryDate)
    const match = result.text.match(/(\d+)/)
    return match ? match[1] : '0'
  },

  updateTabBar() {
    if (typeof this.getTabBar === 'function') {
      const tabBar = this.getTabBar()
      if (tabBar && typeof tabBar.updateSelected === 'function') {
        tabBar.updateSelected('pages/index/index')
      }
    }
  },
})
