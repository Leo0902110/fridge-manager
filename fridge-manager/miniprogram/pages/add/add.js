// pages/add/add.js
const app = getApp()
const api = require('../../utils/api.js')

// 食物类别列表
const CATEGORIES = ['蔬菜', '水果', '肉类', '海鲜', '蛋类', '乳制品', '豆制品', '主食', '其他']

Page({
  data: {
    categories: CATEGORIES,
    categoryIndex: 8, // 默认"其他"
    
    imagePath: '',
    recognitionResults: [],
    selectedIndex: -1,
    
    formData: {
      name: '',
      category: '',
      location: 'fridge',
      shelf_life_days: '',
      notes: '',
    },
    
    autoShelfLife: null,
    recognizing: false,
    submitting: false,
  },

  onLoad() {
    // 加载保质期参考数据
    this.loadShelfLifeReference()
  },

  onShow() {
    this.updateTabBar()
  },

  /**
   * 选择图片
   */
  async chooseImage() {
    if (this.data.recognizing || this.data.submitting) {
      return
    }

    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      camera: 'back',
      success: async (res) => {
        const tempFilePath = res.tempFiles[0].tempFilePath
        this.setData({
          imagePath: tempFilePath,
          recognitionResults: [],
          selectedIndex: -1,
          autoShelfLife: null,
          recognizing: true,
        })
        wx.showNavigationBarLoading()
        
        // 自动识别
        wx.showLoading({ title: 'AI 识别中...' })
        try {
          const result = await api.recognition.recognizeImage(tempFilePath)
          if (result.success && result.data) {
            this.setData({
              recognitionResults: result.data,
              selectedIndex: result.data.length > 0 ? 0 : -1,
            })
            
            // 自动填充第一个结果
            if (result.data.length > 0) {
              this.selectResult({ currentTarget: { dataset: { index: 0 } } })
            }
          }
        } catch (err) {
          console.error('识别失败:', err)
          wx.showToast({
            title: err.message || '识别失败',
            icon: 'none',
          })
        } finally {
          this.setData({ recognizing: false })
          wx.hideLoading()
          wx.hideNavigationBarLoading()
        }
      },
    })
  },

  /**
   * 选择识别结果
   */
  async selectResult(e) {
    if (this.data.submitting || this.data.recognizing) {
      return
    }

    const index = e.currentTarget.dataset.index
    const result = this.data.recognitionResults[index]
    if (!result) {
      return
    }
    
    this.setData({
      selectedIndex: index,
      'formData.name': result.name,
      'formData.category': result.category,
      categoryIndex: CATEGORIES.indexOf(result.category) || 8,
    })
    
    // 查询保质期参考
    try {
      const ref = await api.food.getShelfLifeReference(result.name)
      if (ref.success && ref.data.length > 0) {
        const item = ref.data[0]
        const shelfLife = item.fridge_days || item.freezer_days || item.room_temp_days
        this.setData({
          autoShelfLife: shelfLife,
          'formData.shelf_life_days': shelfLife.toString(),
        })
      }
    } catch (err) {
      console.error('查询保质期失败:', err)
    }
  },

  /**
   * 选择存放位置
   */
  selectLocation(e) {
    if (this.data.submitting) {
      return
    }

    const location = e.currentTarget.dataset.location
    this.setData({
      'formData.location': location,
    })
  },

  /**
   * 输入变化
   */
  onInputChange(e) {
    if (this.data.submitting) {
      return
    }

    const field = e.currentTarget.dataset.field
    const value = e.detail.value
    this.setData({
      [`formData.${field}`]: value,
    })
  },

  /**
   * 类别变化
   */
  onCategoryChange(e) {
    if (this.data.submitting) {
      return
    }

    const index = e.detail.value
    this.setData({
      categoryIndex: index,
      'formData.category': CATEGORIES[index],
    })
  },

  /**
   * 加载保质期参考
   */
  async loadShelfLifeReference() {
    try {
      const ref = await api.food.getShelfLifeReference()
      if (ref.success) {
        console.log('保质期参考数据:', ref.data)
      }
    } catch (err) {
      console.error('加载参考数据失败:', err)
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
   * 提交食物
   */
  async submitFood() {
    const { formData } = this.data

    if (this.data.recognizing) {
      wx.showToast({ title: '请等待识别完成', icon: 'none' })
      return
    }
    
    // 验证
    if (!formData.name.trim()) {
      wx.showToast({ title: '请输入食物名称', icon: 'none' })
      return
    }
    
    if (!formData.shelf_life_days) {
      wx.showToast({ title: '请输入保质期', icon: 'none' })
      return
    }
    
    this.setData({ submitting: true })
    wx.showNavigationBarLoading()
    
    try {
      const res = await api.food.create({
        name: formData.name.trim(),
        category: formData.category || '其他',
        location: formData.location,
        shelf_life_days: parseInt(formData.shelf_life_days),
        notes: formData.notes.trim(),
      })
      
      if (res.success) {
        wx.showToast({
          title: '添加成功',
          icon: 'success',
        })
        
        // 跳转到首页
        setTimeout(() => {
          wx.switchTab({
            url: '/pages/index/index',
          })
        }, 1500)
      }
    } catch (err) {
      console.error('添加失败:', err)
      wx.showToast({
        title: err.message || '添加失败',
        icon: 'none',
      })
    } finally {
      this.setData({ submitting: false })
      wx.hideNavigationBarLoading()
    }
  },

  updateTabBar() {
    if (typeof this.getTabBar === 'function') {
      const tabBar = this.getTabBar()
      if (tabBar && typeof tabBar.updateSelected === 'function') {
        tabBar.updateSelected('pages/add/add')
      }
    }
  },
})
