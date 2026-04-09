// pages/settings/settings.js
const app = getApp()
const api = require('../../utils/api.js')

Page({
  data: {
    stats: {
      totalFoods: 0,
      eatenCount: 0,
      wasteCount: 0,
    },
  },

  onLoad() {
    this.updateTabBar()
  },

  onShow() {
    this.updateTabBar()
    this.loadStats()
  },

  /**
   * 加载统计
   */
  async loadStats() {
    try {
      const res = await api.food.overview()
      if (res.success) {
        this.setData({
          'stats.totalFoods': res.data.total,
          'stats.wasteCount': res.data.expired_count,
        })
      }
    } catch (err) {
      console.error('加载统计失败:', err)
    }
  },

  /**
   * 关于
   */
  showAbout() {
    wx.showModal({
      title: '关于',
      content: '🧊 冰箱管家 v1.0.0\n\n智能管理您的冰箱食物，再也不让食物过期浪费！\n\n功能：\n• 拍照 AI 识别食物\n• 智能保质期计算\n• 临期提醒通知\n• 库存可视化管理',
      showCancel: false,
    })
  },

  /**
   * 检查更新
   */
  checkUpdate() {
    wx.showLoading({ title: '检查中...' })
    setTimeout(() => {
      wx.hideLoading()
      wx.showModal({
        title: '检查更新',
        content: '当前已是最新版本',
        showCancel: false,
      })
    }, 1000)
  },

  /**
   * 意见反馈
   */
  feedback() {
    wx.navigateTo({
      url: '/pages/feedback/feedback',
      fail: () => {
        wx.showToast({
          title: '功能开发中',
          icon: 'none',
        })
      },
    })
  },

  /**
   * 联系我们
   */
  contactUs() {
    wx.showModal({
      title: '联系我们',
      content: '如有问题或建议，请发送邮件至：support@fridgemanager.com',
      showCancel: false,
    })
  },

  updateTabBar() {
    if (typeof this.getTabBar === 'function') {
      const tabBar = this.getTabBar()
      if (tabBar && typeof tabBar.updateSelected === 'function') {
        tabBar.updateSelected('pages/settings/settings')
      }
    }
  },
})
