// pages/detail/detail.js
const app = getApp()
const api = require('../../utils/api.js')

Page({
  data: {
    foodId: null,
    food: null,
    shelfProfile: null,
    storageTip: '',
    daysResult: { text: '', type: 'fresh' },
    loading: true,
    actingType: '',
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ foodId: options.id })
      this.loadFoodDetail()
    }
  },

  onPullDownRefresh() {
    this.loadFoodDetail().finally(() => {
      wx.stopPullDownRefresh()
    })
  },

  /**
   * 加载食物详情
   */
  async loadFoodDetail() {
    this.setData({ loading: true })
    wx.showNavigationBarLoading()

    try {
      const res = await api.food.detail(this.data.foodId)
      if (res.success) {
        const food = res.data
        const daysResult = app.calcDaysLeft(food.expiry_date)
        this.setData({ food, daysResult })
        this.loadShelfProfile(food)
      }
    } catch (err) {
      console.error('加载失败:', err)
      wx.showToast({
        title: err.message || '加载失败',
        icon: 'none',
      })
      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
    } finally {
      this.setData({ loading: false })
      wx.hideNavigationBarLoading()
    }
  },

  /**
   * 获取类别图标
   */
  getCategoryIcon(category) {
    const categories = app.globalData.foodCategories
    return (categories[category] || categories['其他']).icon
  },

  /**
   * 获取位置文本
   */
  getLocationText(location) {
    const map = {
      fridge: '🧊 冷藏',
      freezer: '❄️ 冷冻',
      room: '🏠 常温',
    }
    return map[location] || location
  },

  getLocationDays(location) {
    const profile = this.data.shelfProfile
    if (!profile) {
      return '--'
    }
    return profile[location] || '--'
  },

  async loadShelfProfile(food) {
    try {
      const ref = await api.food.getShelfLifeReference(food.name, food.category)
      if (ref.success && ref.data.length > 0) {
        const shelfRef = ref.data[0]
        this.setData({
          shelfProfile: {
            fridge: shelfRef.fridge_days || 0,
            freezer: shelfRef.freezer_days || 0,
            room: shelfRef.room_temp_days || 0,
          },
          storageTip: shelfRef.storage_tip || '',
        })
      }
    } catch (err) {
      console.error('加载保存建议失败:', err)
    }
  },

  async changeLocation(e) {
    if (this.data.actingType || this.data.loading || !this.data.food) {
      return
    }

    const location = e.currentTarget.dataset.location
    const shelfLife = this.getLocationDays(location)
    if (!shelfLife || shelfLife === '--') {
      wx.showToast({ title: '不推荐这种保存方式', icon: 'none' })
      return
    }

    this.setData({ actingType: 'update' })
    wx.showNavigationBarLoading()
    try {
      const res = await api.food.update(this.data.foodId, {
        location,
        shelf_life_days: Number(shelfLife),
      })
      if (res.success) {
        const food = res.data
        this.setData({
          food,
          daysResult: app.calcDaysLeft(food.expiry_date),
        })
      }
    } catch (err) {
      wx.showToast({ title: err.message || '更新失败', icon: 'none' })
    } finally {
      this.setData({ actingType: '' })
      wx.hideNavigationBarLoading()
    }
  },

  /**
   * 编辑食物
   */
  editFood() {
    if (this.data.actingType || this.data.loading) {
      return
    }

    wx.showToast({ title: '可直接切换保存方式', icon: 'none' })
  },

  /**
   * 删除食物
   */
  async deleteFood() {
    if (this.data.actingType || this.data.loading) {
      return
    }

    wx.showModal({
      title: '确认删除',
      content: '确定要删除这个食物记录吗？',
      success: async (res) => {
        if (res.confirm) {
          this.setData({ actingType: 'delete' })
          wx.showNavigationBarLoading()
          try {
            await api.food.delete(this.data.foodId)
            wx.showToast({
              title: '删除成功',
              icon: 'success',
            })
            setTimeout(() => {
              wx.navigateBack()
            }, 1500)
          } catch (err) {
            this.setData({ actingType: '' })
            wx.showToast({
              title: err.message || '删除失败',
              icon: 'none',
            })
          } finally {
            wx.hideNavigationBarLoading()
          }
        }
      },
    })
  },

  /**
   * 标记为已吃完
   */
  async markAsEaten() {
    if (this.data.actingType || this.data.loading) {
      return
    }

    wx.showModal({
      title: '确认',
      content: '这个食物已经吃完了吗？',
      success: async (res) => {
        if (res.confirm) {
          this.setData({ actingType: 'eat' })
          wx.showNavigationBarLoading()
          try {
            await api.food.delete(this.data.foodId)
            wx.showToast({
              title: '✅ 已记录',
              icon: 'success',
            })
            setTimeout(() => {
              wx.switchTab({
                url: '/pages/index/index',
              })
            }, 1500)
          } catch (err) {
            this.setData({ actingType: '' })
            wx.showToast({
              title: err.message || '操作失败',
              icon: 'none',
            })
          } finally {
            wx.hideNavigationBarLoading()
          }
        }
      },
    })
  },
})
