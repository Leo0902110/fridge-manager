// pages/index/index.js
const app = getApp()
const api = require('../../utils/api.js')
const imageCache = require('../../utils/imageCache.js')

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
    recipeVisible: false,
    recipeLoading: false,
    todayRecipe: null,
    touchStartX: 0,
    touchStartY: 0,
    actionTouchIndex: -1,
    actionTouchMoved: false,
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
              display_image_url: imageCache.getDisplayImageUrl(food.image_url),
            }
          })
          .sort((a, b) => {
            if (a.riskRank !== b.riskRank) {
              return a.riskRank - b.riskRank
            }
            return a.days - b.days
          })

        const expiredFoods = foodList.filter(food => food.riskType === 'expired')
        const actionFoods = foodList
          .filter(food => food.riskType === 'warning' || (food.riskType !== 'expired' && isCookedFood(food) && food.location === 'fridge'))
          .map(food => ({ ...food, swipeOffset: 0, swipeMoving: false, swipeDirection: '' }))
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
        this.resolveDisplayImages(foodList)
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

  async resolveDisplayImages(foodList) {
    const targets = foodList.filter(food => food.image_url && !food.display_image_url)
    if (!targets.length) {
      return
    }

    const token = (this.imageResolveToken || 0) + 1
    this.imageResolveToken = token

    const resolvedItems = await Promise.all(targets.map(async (food) => ({
      id: food.id,
      imageUrl: food.image_url,
      displayUrl: await imageCache.resolveImageUrl(food.image_url),
    })))

    if (this.imageResolveToken !== token) {
      return
    }

    const displayMap = resolvedItems.reduce((map, item) => {
      if (item.displayUrl) {
        map[`${item.id}:${item.imageUrl}`] = item.displayUrl
      }
      return map
    }, {})
    if (!Object.keys(displayMap).length) {
      return
    }

    const hydrateList = (list) => list.map((item) => {
      const displayUrl = displayMap[`${item.id}:${item.image_url}`]
      return displayUrl ? { ...item, display_image_url: displayUrl } : item
    })

    this.setData({
      foodList: hydrateList(this.data.foodList),
      actionFoods: hydrateList(this.data.actionFoods),
      expiredFoods: hydrateList(this.data.expiredFoods),
      activeColdList: hydrateList(this.data.activeColdList),
      freezerList: hydrateList(this.data.freezerList),
      filteredInventory: hydrateList(this.data.filteredInventory),
    })
  },

  onFoodImageError(e) {
    const { id, url } = e.currentTarget.dataset
    if (!id || !url) {
      return
    }

    imageCache.clearImageCache(url)
    const clearImage = (list) => list.map((item) => (
      Number(item.id) === Number(id) && item.image_url === url
        ? { ...item, display_image_url: '' }
        : item
    ))

    const foodList = clearImage(this.data.foodList)
    this.setData({
      foodList,
      actionFoods: clearImage(this.data.actionFoods),
      expiredFoods: clearImage(this.data.expiredFoods),
      activeColdList: clearImage(this.data.activeColdList),
      freezerList: clearImage(this.data.freezerList),
      filteredInventory: clearImage(this.data.filteredInventory),
    })

    this.resolveDisplayImages(foodList)
  },

  onActionTouchStart(e) {
    const index = Number(e.currentTarget.dataset.index)
    this.resetActionSwipe(index)
    this.setData({
      touchStartX: e.changedTouches[0].clientX,
      touchStartY: e.changedTouches[0].clientY,
      actionTouchIndex: index,
      actionTouchMoved: false,
      [`actionFoods[${index}].swipeMoving`]: true,
    })
  },

  onActionTouchMove(e) {
    const index = Number(e.currentTarget.dataset.index)
    if (index !== this.data.actionTouchIndex || !this.data.actionFoods[index]) {
      return
    }

    const touch = e.changedTouches[0]
    const deltaX = touch.clientX - this.data.touchStartX
    const deltaY = touch.clientY - this.data.touchStartY
    if (Math.abs(deltaY) > Math.abs(deltaX) && Math.abs(deltaY) > 10) {
      return
    }

    const maxOffset = 118
    const offset = Math.max(-maxOffset, Math.min(maxOffset, deltaX))
    const direction = offset > 8 ? 'eat' : offset < -8 ? 'discard' : ''

    this.setData({
      actionTouchMoved: Math.abs(offset) > 10,
      [`actionFoods[${index}].swipeOffset`]: offset,
      [`actionFoods[${index}].swipeDirection`]: direction,
    })
  },

  onActionTouchEnd(e) {
    const index = Number(e.currentTarget.dataset.index)
    const item = this.data.actionFoods[index]
    if (!item) {
      return
    }

    const offset = Number(item.swipeOffset || 0)
    const threshold = 72
    if (offset > threshold) {
      this.animateActionCommit(index, 'eat')
    } else if (offset < -threshold) {
      this.animateActionCommit(index, 'discard')
    } else {
      if (this.data.actionTouchMoved) {
        this.suppressActionTapUntil = Date.now() + 320
      }
      this.resetActionSwipe(index)
    }
  },

  handleActionTap(e) {
    if (this.data.actionTouchMoved || Date.now() < (this.suppressActionTapUntil || 0)) {
      const index = Number(e.currentTarget.dataset.index)
      this.resetActionSwipe(index)
      return
    }
    this.goToDetail(e)
  },

  resetActionSwipe(index = -1) {
    const updates = {
      actionTouchIndex: -1,
      actionTouchMoved: false,
    }
    const resetOne = (itemIndex) => {
      if (itemIndex >= 0 && this.data.actionFoods[itemIndex]) {
        updates[`actionFoods[${itemIndex}].swipeOffset`] = 0
        updates[`actionFoods[${itemIndex}].swipeMoving`] = false
        updates[`actionFoods[${itemIndex}].swipeDirection`] = ''
      }
    }

    if (index >= 0) {
      resetOne(index)
    } else {
      this.data.actionFoods.forEach((_, itemIndex) => resetOne(itemIndex))
    }
    this.setData(updates)
  },

  animateActionCommit(index, type) {
    const item = this.data.actionFoods[index]
    if (!item) {
      return
    }
    const commitOffset = type === 'discard' ? -180 : 180
    this.setData({
      [`actionFoods[${index}].swipeOffset`]: commitOffset,
      [`actionFoods[${index}].swipeMoving`]: false,
      [`actionFoods[${index}].swipeDirection`]: type,
      actionTouchIndex: -1,
      actionTouchMoved: true,
    })
    this.suppressActionTapUntil = Date.now() + 500
    setTimeout(() => {
      this.completeFood(item.id, type)
    }, 180)
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

  async generateTodayRecipe() {
    if (this.data.recipeLoading) {
      return
    }

    this.setData({
      recipeVisible: true,
      recipeLoading: true,
      todayRecipe: null,
    })

    try {
      const res = await api.food.todayRecipe()
      if (res.success) {
        this.setData({
          todayRecipe: res.data,
        })
      } else {
        throw new Error(res.message || '菜谱生成失败')
      }
    } catch (err) {
      wx.showToast({
        title: err.message || '菜谱生成失败',
        icon: 'none',
      })
      this.setData({
        recipeVisible: false,
      })
    } finally {
      this.setData({
        recipeLoading: false,
      })
    }
  },

  closeRecipeSheet() {
    this.setData({
      recipeVisible: false,
    })
  },

  noop() {},

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
