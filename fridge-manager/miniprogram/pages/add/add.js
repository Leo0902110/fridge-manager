// pages/add/add.js
const app = getApp()
const api = require('../../utils/api.js')

const CATEGORIES = ['蔬菜', '水果', '肉类', '海鲜', '蛋类', '乳制品', '豆制品', '主食', '熟食', '剩菜', '其他']

function defaultCategoryIndex(category) {
  const index = CATEGORIES.indexOf(category)
  return index >= 0 ? index : CATEGORIES.length - 1
}

function buildSelectedItem(result, sourceIndex, imagePath) {
  const category = result.category || '其他'
  return {
    sourceIndex,
    name: result.name || '',
    category,
    categoryIndex: defaultCategoryIndex(category),
    confidence: result.confidence || 80,
    shelf_life_days: '',
    notes: '',
    imagePath: '',
    cropStatus: imagePath ? '待裁剪' : '无图片',
  }
}

Page({
  data: {
    categories: CATEGORIES,
    categoryIndex: CATEGORIES.length - 1,

    imagePath: '',
    recognitionResults: [],
    selectedItems: [],
    selectedCount: 0,

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
    this.loadShelfLifeReference()
  },

  onShow() {
    this.updateTabBar()
  },

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
          selectedItems: [],
          selectedCount: 0,
          autoShelfLife: null,
          recognizing: true,
        })
        wx.showNavigationBarLoading()

        wx.showLoading({ title: 'AI 识别中...' })
        try {
          const result = await api.recognition.recognizeImage(tempFilePath)
          const results = (result.success && result.data ? result.data : []).map((item, index) => ({
            ...item,
            selected: true,
            sourceIndex: index,
          }))
          const selectedItems = results.map((item, index) => buildSelectedItem(item, index, tempFilePath))

          this.setData({
            recognitionResults: results,
            selectedItems,
            selectedCount: selectedItems.length,
          })

          if (selectedItems.length > 0) {
            await this.fillShelfLifeForSelected()
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

  toggleResult(e) {
    if (this.data.submitting || this.data.recognizing) {
      return
    }

    const index = Number(e.currentTarget.dataset.index)
    const results = this.data.recognitionResults.slice()
    const result = results[index]
    if (!result) {
      return
    }

    result.selected = !result.selected
    let selectedItems = this.data.selectedItems.slice()
    if (result.selected) {
      selectedItems.push(buildSelectedItem(result, index, this.data.imagePath))
    } else {
      selectedItems = selectedItems.filter(item => item.sourceIndex !== index)
    }

    this.setData({
      recognitionResults: results,
      selectedItems,
      selectedCount: selectedItems.length,
    })

    if (result.selected) {
      this.fillShelfLifeForItem(selectedItems.length - 1)
    }
  },

  async fillShelfLifeForSelected() {
    for (let i = 0; i < this.data.selectedItems.length; i += 1) {
      await this.fillShelfLifeForItem(i)
    }
  },

  async fillShelfLifeForItem(index) {
    const item = this.data.selectedItems[index]
    if (!item || !item.name) {
      return
    }

    try {
      const ref = await api.food.getShelfLifeReference(item.name)
      if (ref.success && ref.data.length > 0) {
        const shelfRef = ref.data[0]
        const shelfLife = shelfRef.fridge_days || shelfRef.freezer_days || shelfRef.room_temp_days || 7
        this.setData({
          [`selectedItems[${index}].shelf_life_days`]: String(shelfLife),
        })
      } else {
        this.setData({
          [`selectedItems[${index}].shelf_life_days`]: '7',
        })
      }
    } catch (err) {
      console.error('查询保质期失败:', err)
      this.setData({
        [`selectedItems[${index}].shelf_life_days`]: '7',
      })
    }
  },

  cropSelectedImage(e) {
    if (this.data.submitting || !this.data.imagePath) {
      return
    }

    const index = Number(e.currentTarget.dataset.index)
    if (!this.data.selectedItems[index]) {
      return
    }

    if (typeof wx.cropImage !== 'function') {
      wx.showToast({
        title: '当前微信版本不支持裁剪',
        icon: 'none',
      })
      return
    }

    wx.cropImage({
      src: this.data.imagePath,
      cropScale: '1:1',
      success: (res) => {
        this.setData({
          [`selectedItems[${index}].imagePath`]: res.tempFilePath,
          [`selectedItems[${index}].cropStatus`]: '已裁剪',
        })
      },
      fail: (err) => {
        if (!String(err.errMsg || '').includes('cancel')) {
          wx.showToast({
            title: '裁剪失败',
            icon: 'none',
          })
        }
      },
    })
  },

  removeSelectedItem(e) {
    if (this.data.submitting) {
      return
    }

    const index = Number(e.currentTarget.dataset.index)
    const selectedItems = this.data.selectedItems.slice()
    const [removed] = selectedItems.splice(index, 1)
    const recognitionResults = this.data.recognitionResults.slice()
    if (removed && recognitionResults[removed.sourceIndex]) {
      recognitionResults[removed.sourceIndex].selected = false
    }

    this.setData({
      selectedItems,
      recognitionResults,
      selectedCount: selectedItems.length,
    })
  },

  selectLocation(e) {
    if (this.data.submitting) {
      return
    }

    const location = e.currentTarget.dataset.location
    this.setData({
      'formData.location': location,
    })
  },

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

  onSelectedInputChange(e) {
    if (this.data.submitting) {
      return
    }

    const index = Number(e.currentTarget.dataset.index)
    const field = e.currentTarget.dataset.field
    this.setData({
      [`selectedItems[${index}].${field}`]: e.detail.value,
    })
  },

  onCategoryChange(e) {
    if (this.data.submitting) {
      return
    }

    const index = Number(e.detail.value)
    this.setData({
      categoryIndex: index,
      'formData.category': CATEGORIES[index],
    })
  },

  onSelectedCategoryChange(e) {
    if (this.data.submitting) {
      return
    }

    const itemIndex = Number(e.currentTarget.dataset.index)
    const categoryIndex = Number(e.detail.value)
    this.setData({
      [`selectedItems[${itemIndex}].categoryIndex`]: categoryIndex,
      [`selectedItems[${itemIndex}].category`]: CATEGORIES[categoryIndex],
    })
  },

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

  getCategoryIcon(category) {
    const categories = app.globalData.foodCategories
    return (categories[category] || categories['其他']).icon
  },

  async uploadItemImage(item) {
    const imagePath = item.imagePath || this.data.imagePath
    if (!imagePath) {
      return ''
    }

    const uploadRes = await api.food.uploadImage(imagePath)
    return uploadRes.data && uploadRes.data.image_url ? uploadRes.data.image_url : ''
  },

  async submitFood() {
    if (this.data.recognizing) {
      wx.showToast({ title: '请等待识别完成', icon: 'none' })
      return
    }

    const selectedItems = this.data.selectedItems
    const isBatch = selectedItems.length > 0

    if (!isBatch && !this.data.formData.name.trim()) {
      wx.showToast({ title: '请输入食物名称', icon: 'none' })
      return
    }

    if (!isBatch && !this.data.formData.shelf_life_days) {
      wx.showToast({ title: '请输入保质期', icon: 'none' })
      return
    }

    for (let i = 0; i < selectedItems.length; i += 1) {
      if (!selectedItems[i].name.trim()) {
        wx.showToast({ title: `请补充第 ${i + 1} 项名称`, icon: 'none' })
        return
      }
      if (!selectedItems[i].shelf_life_days) {
        wx.showToast({ title: `请补充第 ${i + 1} 项保质期`, icon: 'none' })
        return
      }
    }

    this.setData({ submitting: true })
    wx.showNavigationBarLoading()

    try {
      if (isBatch) {
        wx.showLoading({ title: `保存 0/${selectedItems.length}` })
        for (let i = 0; i < selectedItems.length; i += 1) {
          const item = selectedItems[i]
          wx.showLoading({ title: `保存 ${i + 1}/${selectedItems.length}` })
          const imageUrl = await this.uploadItemImage(item)
          await api.food.create({
            name: item.name.trim(),
            category: item.category || '其他',
            image_url: imageUrl,
            location: this.data.formData.location,
            shelf_life_days: parseInt(item.shelf_life_days, 10),
            notes: item.notes.trim(),
          })
        }
      } else {
        const res = await api.food.create({
          name: this.data.formData.name.trim(),
          category: this.data.formData.category || '其他',
          location: this.data.formData.location,
          shelf_life_days: parseInt(this.data.formData.shelf_life_days, 10),
          notes: this.data.formData.notes.trim(),
        })
        if (!res.success) {
          throw new Error(res.message || '添加失败')
        }
      }

      wx.showToast({
        title: isBatch ? '批量添加成功' : '添加成功',
        icon: 'success',
      })

      setTimeout(() => {
        wx.switchTab({
          url: '/pages/index/index',
        })
      }, 1200)
    } catch (err) {
      console.error('添加失败:', err)
      wx.showToast({
        title: err.message || '添加失败',
        icon: 'none',
      })
    } finally {
      this.setData({ submitting: false })
      wx.hideLoading()
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
