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

function isCookedFood(food) {
  return ['熟食', '剩菜'].includes(food.category)
}

Page({
  data: {
    stats: {
      total: 0,
      fresh_count: 0,
      warning_count: 0,
      expired_count: 0,
    },
    foodList: [],
    actionFoods: [],
    expiredFoods: [],
    activeColdList: [],
    freezerList: [],
    filteredInventory: [],
    inventoryZone: 'fridge',
    quickFilter: 'all',
    undoVisible: false,
    undoText: '',
    undoFood: null,
    undoEventId: null,
    touchStartX: 0,
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
    this.updateTabBar()
    const dirty = typeof app.consumeFoodListDirty === 'function'
      ? app.consumeFoodListDirty()
      : !!app.globalData.foodListDirty
    const isStale = !this.lastLoadAt || Date.now() - this.lastLoadAt > 30000
    if (!this.data.initialized || dirty || isStale) {
      this.loadData({ silent: this.data.initialized && !dirty })
    }
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
    const { refresh = false, silent = false } = options

    this.setData({
      loading: !silent,
      refreshing: refresh,
      lastUpdatedText: refresh ? '刷新中' : '正在同步',
    })
    if (!silent) {
      wx.showNavigationBarLoading()
    }
    
    try {
      const listParams = this.data.filter === 'warning' ? { status: 'warning' } : {}
      const [overviewRes, listRes] = await Promise.all([
        api.food.overview(),
        api.food.list(listParams),
      ])

      if (overviewRes.success) {
        this.setData({
          stats: overviewRes.data,
        })
      }
      
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

        const expiredFoods = foodList.filter(food => food.riskType === 'expired')
        const actionFoods = foodList.filter(food => food.riskType === 'warning' || (food.riskType !== 'expired' && isCookedFood(food) && food.location === 'fridge'))
        const activeColdList = foodList.filter(food => food.location !== 'freezer')
        const freezerList = foodList.filter(food => food.location === 'freezer')
        const filteredInventory = this.filterInventory(this.data.inventoryZone, this.data.quickFilter, activeColdList, freezerList)

        this.setData({
          foodList,
          actionFoods,
          expiredFoods,
          activeColdList,
          freezerList,
          filteredInventory,
        })
      }

      this.setData({
        initialized: true,
        lastUpdatedText: `刚刚更新`,
      })
      this.lastLoadAt = Date.now()
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
      if (!silent) {
        wx.hideNavigationBarLoading()
      }
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

  setInventoryZone(e) {
    const inventoryZone = e.currentTarget.dataset.zone
    this.setData({
      inventoryZone,
      filteredInventory: this.filterInventory(inventoryZone, this.data.quickFilter),
    })
  },

  setQuickFilter(e) {
    const quickFilter = e.currentTarget.dataset.filter
    this.setData({
      quickFilter,
      filteredInventory: this.filterInventory(this.data.inventoryZone, quickFilter),
    })
  },

  filterInventory(zone, quickFilter, activeColdList = this.data.activeColdList, freezerList = this.data.freezerList) {
    const source = zone === 'freezer' ? freezerList : activeColdList
    if (quickFilter === 'all') {
      return source
    }
    if (quickFilter === 'warning') {
      return source.filter(food => food.riskType === 'warning' || food.riskType === 'expired')
    }
    return source.filter(food => food.category === quickFilter)
  },

  onActionTouchStart(e) {
    this.setData({
      touchStartX: e.changedTouches[0].clientX,
    })
  },

  onActionTouchEnd(e) {
    const deltaX = e.changedTouches[0].clientX - this.data.touchStartX
    const id = e.currentTarget.dataset.id
    if (deltaX > 80) {
      this.completeFood(id, 'eat')
    } else if (deltaX < -80) {
      this.completeFood(id, 'discard')
    }
  },

  async completeFood(id, type) {
    const food = this.data.foodList.find(item => Number(item.id) === Number(id))
    if (!food) {
      return
    }

    try {
      const completeRes = await api.food.complete(id, type === 'discard' ? 'discard' : 'eat')
      const verb = type === 'discard' ? '丢弃' : '吃完'
      this.setData({
        undoVisible: true,
        undoText: `已记录${verb}${food.name}`,
        undoFood: food,
        undoEventId: completeRes.data ? completeRes.data.event_id : null,
      })
      clearTimeout(this.undoTimer)
      this.undoTimer = setTimeout(() => {
        this.setData({ undoVisible: false, undoFood: null, undoEventId: null })
      }, 3000)
      this.loadData()
    } catch (err) {
      wx.showToast({ title: err.message || '操作失败', icon: 'none' })
    }
  },

  async undoLastAction() {
    const { undoFood: food, undoEventId } = this.data
    if (!food) {
      return
    }
    clearTimeout(this.undoTimer)
    try {
      await api.food.create({
        name: food.name,
        category: food.category,
        image_url: food.image_url,
        put_date: food.put_date,
        location: food.location,
        shelf_life_days: food.shelf_life_days,
        notes: food.notes || '',
      })
      if (undoEventId) {
        await api.food.deleteEvent(undoEventId)
      }
      this.setData({ undoVisible: false, undoFood: null, undoEventId: null })
      this.loadData()
    } catch (err) {
      wx.showToast({ title: err.message || '撤销失败', icon: 'none' })
    }
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

  updateTabBar() {
    if (typeof this.getTabBar === 'function') {
      const tabBar = this.getTabBar()
      if (tabBar && typeof tabBar.updateSelected === 'function') {
        tabBar.updateSelected('pages/index/index')
      }
    }
  },
})
