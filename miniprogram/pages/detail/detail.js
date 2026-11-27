// pages/detail/detail.js
const app = getApp()
const api = require('../../utils/api.js')
const imageCache = require('../../utils/imageCache.js')

const LOCATION_LABELS = {
  fridge: '冷藏',
  freezer: '冷冻',
  room: '常温',
}

function buildShelfExplain(food, shelfProfile, storageTip) {
  if (!food) {
    return ''
  }
  const locationText = LOCATION_LABELS[food.location] || '冷藏'
  const days = food.shelf_life_days || (shelfProfile && shelfProfile[food.location]) || ''
  const sourceText = shelfProfile ? '参考库' : '当前记录'
  const tip = storageTip ? `，${storageTip}` : ''
  return `${sourceText}判断：${food.name || '该食材'}属于${food.category || '食材'}，当前按${locationText}保存，所以建议约 ${days || '--'} 天${tip}。`
}

Page({
  data: {
    foodId: null,
    food: null,
    shelfProfile: null,
    storageTip: '',
    shelfExplainText: '',
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
        const food = this.decorateFood(res.data)
        const daysResult = app.calcDaysLeft(food.expiry_date)
        this.setData({
          food,
          daysResult,
          shelfExplainText: buildShelfExplain(food, this.data.shelfProfile, this.data.storageTip),
        })
        this.resolveDisplayImage(food.image_url)
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

  decorateFood(food) {
    return {
      ...food,
      display_image_url: imageCache.getDisplayImageUrl(food.image_url),
    }
  },

  async resolveDisplayImage(imageUrl) {
    if (!imageUrl || imageCache.getDisplayImageUrl(imageUrl)) {
      return
    }

    const token = (this.imageResolveToken || 0) + 1
    this.imageResolveToken = token
    const displayUrl = await imageCache.resolveImageUrl(imageUrl)
    if (this.imageResolveToken === token && displayUrl && this.data.food && this.data.food.image_url === imageUrl) {
      this.setData({
        'food.display_image_url': displayUrl,
      })
    }
  },

  onFoodImageError(e) {
    const { url } = e.currentTarget.dataset
    if (!url || !this.data.food || this.data.food.image_url !== url) {
      return
    }

    imageCache.clearImageCache(url)
    this.setData({
      'food.display_image_url': '',
    })
    this.resolveDisplayImage(url)
  },

  async loadShelfProfile(food) {
    try {
      const ref = await api.food.getShelfLifeReference(food.name, food.category)
      if (ref.success && ref.data.length > 0) {
        const shelfRef = ref.data[0]
        const shelfProfile = {
          fridge: shelfRef.fridge_days || 0,
          freezer: shelfRef.freezer_days || 0,
          room: shelfRef.room_temp_days || 0,
        }
        const storageTip = shelfRef.storage_tip || ''
        this.setData({
          shelfProfile,
          storageTip,
          shelfExplainText: buildShelfExplain(food, shelfProfile, storageTip),
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
        const food = this.decorateFood(res.data)
        this.setData({
          food,
          daysResult: app.calcDaysLeft(food.expiry_date),
          shelfExplainText: buildShelfExplain(food, this.data.shelfProfile, this.data.storageTip),
        })
        this.resolveDisplayImage(food.image_url)
        if (typeof app.markFoodListDirty === 'function') {
          app.markFoodListDirty()
        }
      }
    } catch (err) {
      wx.showToast({ title: err.message || '更新失败', icon: 'none' })
    } finally {
      this.setData({ actingType: '' })
      wx.hideNavigationBarLoading()
    }
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
            if (typeof app.markFoodListDirty === 'function') {
              app.markFoodListDirty()
            }
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
            await api.food.complete(this.data.foodId, 'eat')
            if (typeof app.markFoodListDirty === 'function') {
              app.markFoodListDirty()
            }
            wx.showToast({
              title: '✅ 已记录',
              icon: 'success',
            })
            const goHome = () => {
              wx.switchTab({
                url: '/pages/index/index',
              })
            }
            if (typeof app.scheduleNavigation === 'function') {
              app.scheduleNavigation(goHome, 900)
            } else {
              setTimeout(goHome, 900)
            }
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
