// pages/add/add.js
const app = getApp()
const api = require('../../utils/api.js')

const CATEGORIES = ['蔬菜', '水果', '肉类', '海鲜', '蛋类', '乳制品', '豆制品', '主食', '熟食', '剩菜', '其他']
const COOKED_KEYWORDS = ['熟食', '剩菜', '便当', '餐盘', '拼盘', '套餐', '盒饭', '饭盒', '炒菜', '炒饭', '盖饭', '剩饭', '汤']
const LOCATION_LABELS = {
  fridge: '冷藏',
  freezer: '冷冻',
  room: '常温',
}

function defaultCategoryIndex(category) {
  const index = CATEGORIES.indexOf(category)
  return index >= 0 ? index : CATEGORIES.length - 1
}

function buildSelectedItem(result, sourceIndex, imagePath) {
  const category = result.category || '其他'
  const shelfLife = result.shelf_life_days || getDefaultShelfLife(result.name, category)
  const recommendedLocation = result.recommended_location || getDefaultLocation(result.name, category)
  return {
    sourceIndex,
    name: result.name || '',
    category,
    categoryIndex: defaultCategoryIndex(category),
    confidence: result.confidence || 80,
    shelf_life_days: shelfLife ? String(shelfLife) : '',
    shelfProfile: result.shelfProfile || null,
    recommended_location: recommendedLocation,
    storage_tip: result.storage_tip || getDefaultStorageTip(result.name, category, recommendedLocation),
    notes: '',
    imagePath: '',
    cropStatus: imagePath ? '使用原图' : '无图片',
  }
}

function getDefaultShelfLife(name, category) {
  const text = `${name || ''}${category || ''}`
  if (category === '熟食' || category === '剩菜' || COOKED_KEYWORDS.some(keyword => text.indexOf(keyword) >= 0)) {
    return 2
  }
  return ''
}

function getDefaultLocation(name, category) {
  const text = `${name || ''}${category || ''}`
  if (category === '肉类' || category === '海鲜') {
    return 'freezer'
  }
  if (['土豆', '洋葱', '大蒜', '姜', '香蕉', '面包'].some(keyword => text.indexOf(keyword) >= 0)) {
    return 'room'
  }
  return 'fridge'
}

function getDefaultStorageTip(name, category, location) {
  if (category === '熟食' || category === '剩菜') {
    return '按整份熟食管理，建议两天内吃完'
  }
  if (location === 'freezer') {
    return '短期不吃建议分装冷冻'
  }
  if (location === 'room') {
    return '阴凉通风保存，切开后冷藏'
  }
  return '冷藏保存，尽快食用'
}

function buildShelfProfile(ref) {
  return {
    fridge: ref.fridge_days || 0,
    freezer: ref.freezer_days || 0,
    room: ref.room_temp_days || 0,
  }
}

function getShelfLifeByLocation(profile, location) {
  if (!profile) {
    return ''
  }
  return profile[location] || profile.fridge || profile.freezer || profile.room || ''
}

function calcExpiryDate(days) {
  const date = new Date()
  date.setDate(date.getDate() + Number(days || 0))
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

Page({
  data: {
    categories: CATEGORIES,
    categoryIndex: CATEGORIES.length - 1,

    imagePath: '',
    recognitionResults: [],
    wholeItem: null,
    entryMode: 'split',
    modeReason: '',
    selectedItems: [],
    selectedCount: 0,
    editorVisible: false,
    decisionVisible: false,
    decisionInfoOpen: false,
    decisionSource: '',
    decisionIndex: -1,
    decisionItem: null,
    editingIndex: -1,
    editDraft: null,

    formData: {
      name: '',
      category: '',
      location: 'fridge',
      shelf_life_days: '',
      notes: '',
    },

    autoShelfLife: null,
    storageSuggestion: '',
    manualShelfProfile: null,
    manualRecommendedLocation: '',
    manualStorageTip: '',
    recognizing: false,
    submitting: false,
  },

  onLoad() {
    this.manualLookupSeq = 0
    this.loadShelfLifeReference()
  },

  onShow() {
    this.updateTabBar()
  },

  noop() {},

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
          wholeItem: null,
          entryMode: 'split',
          modeReason: '',
          selectedItems: [],
          selectedCount: 0,
          autoShelfLife: null,
          recognizing: true,
        })
        wx.showNavigationBarLoading()

        wx.showLoading({ title: 'AI 识别中...' })
        let errorMessage = ''
        try {
          const result = await api.recognition.recognizeImage(tempFilePath)
          const results = (result.success && result.data ? result.data : []).map((item, index) => ({
            ...item,
            selected: result.mode !== 'whole',
            sourceIndex: index,
          }))
          const wholeItem = result.whole_food ? buildSelectedItem(result.whole_food, -1, tempFilePath) : null
          const shouldUseWhole = result.mode === 'whole' && wholeItem
          const selectedItems = shouldUseWhole
            ? [wholeItem]
            : results.map((item, index) => buildSelectedItem(item, index, tempFilePath))

          this.setData({
            recognitionResults: results,
            wholeItem,
            entryMode: shouldUseWhole ? 'whole' : 'split',
            modeReason: result.mode_reason || '',
            selectedItems,
            selectedCount: selectedItems.length,
          })

          if (selectedItems.length > 0) {
            await this.fillShelfLifeForSelected()
            this.openDecisionSheet(shouldUseWhole ? 'whole' : 'item', 0)
          }
        } catch (err) {
          console.error('识别失败:', err)
          errorMessage = err.message || '识别失败'
        } finally {
          this.setData({ recognizing: false })
          wx.hideLoading()
          wx.hideNavigationBarLoading()
          if (errorMessage) {
            wx.showToast({
              title: errorMessage,
              icon: 'none',
            })
          }
        }
      },
    })
  },

  switchEntryMode(e) {
    if (this.data.submitting || this.data.recognizing) {
      return
    }

    const mode = e.currentTarget.dataset.mode
    if (mode === this.data.entryMode) {
      return
    }

    const results = this.data.recognitionResults.map(item => ({
      ...item,
      selected: mode === 'split',
    }))
    const selectedItems = mode === 'whole' && this.data.wholeItem
      ? [{ ...this.data.wholeItem }]
      : results.map((item, index) => buildSelectedItem(item, index, this.data.imagePath))

    this.setData({
      entryMode: mode,
      recognitionResults: results,
      selectedItems,
      selectedCount: selectedItems.length,
    })

    this.fillShelfLifeForSelected()
    this.openDecisionSheet(mode === 'whole' ? 'whole' : 'item', 0)
  },

  toggleResult(e) {
    if (this.data.submitting || this.data.recognizing) {
      return
    }

    if (this.data.entryMode !== 'split') {
      this.switchEntryMode({ currentTarget: { dataset: { mode: 'split' } } })
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

    const defaultShelfLife = getDefaultShelfLife(item.name, item.category)
    if (!item.shelf_life_days && defaultShelfLife) {
      this.setData({
        [`selectedItems[${index}].shelf_life_days`]: String(defaultShelfLife),
      })
    }

    try {
      const ref = await api.food.getShelfLifeReference(item.name, item.category)
      if (ref.success && ref.data.length > 0) {
        const shelfRef = ref.data[0]
        const profile = buildShelfProfile(shelfRef)
        const shelfLife = getShelfLifeByLocation(profile, this.data.formData.location) || item.shelf_life_days || 7
        this.setData({
          [`selectedItems[${index}].shelf_life_days`]: String(shelfLife),
          [`selectedItems[${index}].shelfProfile`]: profile,
          [`selectedItems[${index}].recommended_location`]: shelfRef.recommended_location || item.recommended_location,
          [`selectedItems[${index}].storage_tip`]: shelfRef.storage_tip || item.storage_tip,
        })
      } else if (!item.shelf_life_days) {
        this.setData({
          [`selectedItems[${index}].shelf_life_days`]: '7',
        })
      }
    } catch (err) {
      console.error('查询保质期失败:', err)
      if (!item.shelf_life_days) {
        this.setData({
          [`selectedItems[${index}].shelf_life_days`]: '7',
        })
      }
    }
  },

  buildDecisionItem(item, source) {
    const profile = item.shelfProfile || (source === 'manual' ? this.data.manualShelfProfile : null) || {}
    const location = source === 'manual' ? this.data.formData.location : this.data.formData.location
    const shelfLife = getShelfLifeByLocation(profile, location) || item.shelf_life_days || this.data.formData.shelf_life_days
    return {
      ...item,
      source,
      shelfProfile: profile,
      location,
      shelf_life_days: shelfLife ? String(shelfLife) : '',
      expiryPreview: shelfLife ? calcExpiryDate(shelfLife) : '',
      recommended_location: item.recommended_location || this.data.manualRecommendedLocation || getDefaultLocation(item.name, item.category),
      storage_tip: item.storage_tip || this.data.manualStorageTip || getDefaultStorageTip(item.name, item.category, location),
    }
  },

  openDecisionSheet(source, index = -1) {
    if (this.data.submitting || this.data.recognizing) {
      return
    }

    const item = source === 'manual'
      ? {
          name: this.data.formData.name,
          category: this.data.formData.category || CATEGORIES[this.data.categoryIndex] || '其他',
          shelf_life_days: this.data.formData.shelf_life_days,
          shelfProfile: this.data.manualShelfProfile,
          recommended_location: this.data.manualRecommendedLocation,
          storage_tip: this.data.manualStorageTip,
        }
      : this.data.selectedItems[index]

    if (!item || !item.name) {
      return
    }

    this.setData({
      decisionVisible: true,
      decisionInfoOpen: false,
      decisionSource: source,
      decisionIndex: index,
      decisionItem: this.buildDecisionItem(item, source),
    })
  },

  closeDecisionSheet() {
    this.setData({
      decisionVisible: false,
      decisionInfoOpen: false,
      decisionSource: '',
      decisionIndex: -1,
      decisionItem: null,
    })
  },

  toggleDecisionInfo() {
    this.setData({
      decisionInfoOpen: !this.data.decisionInfoOpen,
    })
  },

  selectDecisionLocation(e) {
    const location = e.currentTarget.dataset.location
    const item = this.data.decisionItem
    if (!item) {
      return
    }

    const shelfLife = getShelfLifeByLocation(item.shelfProfile, location) || item.shelf_life_days
    this.setData({
      'decisionItem.location': location,
      'decisionItem.shelf_life_days': shelfLife ? String(shelfLife) : '',
      'decisionItem.expiryPreview': shelfLife ? calcExpiryDate(shelfLife) : '',
    })
  },

  confirmDecision() {
    const item = this.data.decisionItem
    if (!item) {
      return
    }

    if (this.data.decisionSource === 'manual') {
      this.setData({
        'formData.location': item.location,
        'formData.shelf_life_days': item.shelf_life_days,
        storageSuggestion: `${LOCATION_LABELS[item.recommended_location] || '冷藏'} · ${item.storage_tip}`,
      })
    } else if (this.data.decisionIndex >= 0) {
      this.setData({
        [`selectedItems[${this.data.decisionIndex}].shelf_life_days`]: item.shelf_life_days,
        [`selectedItems[${this.data.decisionIndex}].recommended_location`]: item.recommended_location,
        [`selectedItems[${this.data.decisionIndex}].storage_tip`]: item.storage_tip,
        [`selectedItems[${this.data.decisionIndex}].shelfProfile`]: item.shelfProfile,
        'formData.location': item.location,
      })
      this.applyLocationShelfLife(item.location)
    }

    this.closeDecisionSheet()
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

  cropEditingImage() {
    if (this.data.submitting || !this.data.imagePath || !this.data.editDraft) {
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
          'editDraft.imagePath': res.tempFilePath,
          'editDraft.cropStatus': '已裁剪',
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

  openItemEditor(e) {
    if (this.data.submitting) {
      return
    }

    const index = Number(e.currentTarget.dataset.index)
    const item = this.data.selectedItems[index]
    if (!item) {
      return
    }

    this.setData({
      editorVisible: true,
      editingIndex: index,
      editDraft: { ...item },
    })
  },

  closeItemEditor() {
    if (this.data.submitting) {
      return
    }

    this.setData({
      editorVisible: false,
      editingIndex: -1,
      editDraft: null,
    })
  },

  saveEditingItem() {
    const { editingIndex, editDraft } = this.data
    if (editingIndex < 0 || !editDraft) {
      return
    }

    if (!editDraft.name.trim()) {
      wx.showToast({ title: '请输入食物名称', icon: 'none' })
      return
    }

    if (!editDraft.shelf_life_days) {
      wx.showToast({ title: '请输入保质期', icon: 'none' })
      return
    }

    this.setData({
      [`selectedItems[${editingIndex}]`]: {
        ...editDraft,
        name: editDraft.name.trim(),
        notes: (editDraft.notes || '').trim(),
      },
      editorVisible: false,
      editingIndex: -1,
      editDraft: null,
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
    this.applyLocationShelfLife(location)
    if (this.data.formData.name.trim()) {
      this.fillManualShelfLife()
    }
  },

  applyLocationShelfLife(location) {
    const updates = {}
    this.data.selectedItems.forEach((item, index) => {
      const shelfLife = getShelfLifeByLocation(item.shelfProfile, location)
      if (shelfLife) {
        updates[`selectedItems[${index}].shelf_life_days`] = String(shelfLife)
      }
    })
    if (Object.keys(updates).length > 0) {
      this.setData(updates)
    }
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
    if (field === 'name' && value.trim()) {
      this.fillManualShelfLife()
    }
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

  onEditDraftInputChange(e) {
    if (this.data.submitting || !this.data.editDraft) {
      return
    }

    const field = e.currentTarget.dataset.field
    this.setData({
      [`editDraft.${field}`]: e.detail.value,
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
    if (this.data.formData.name.trim()) {
      this.fillManualShelfLife()
    }
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

  onEditDraftCategoryChange(e) {
    if (this.data.submitting || !this.data.editDraft) {
      return
    }

    const categoryIndex = Number(e.detail.value)
    this.setData({
      'editDraft.categoryIndex': categoryIndex,
      'editDraft.category': CATEGORIES[categoryIndex],
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

  getLocationText(location) {
    return LOCATION_LABELS[location] || '冷藏'
  },

  async fillManualShelfLife() {
    const name = this.data.formData.name.trim()
    if (!name) {
      return
    }
    const lookupSeq = (this.manualLookupSeq || 0) + 1
    this.manualLookupSeq = lookupSeq

    try {
      let category = this.data.formData.category
      if (!category || category === '其他') {
        const recognized = await api.recognition.recognizeByName(name)
        if (lookupSeq !== this.manualLookupSeq) {
          return
        }
        if (recognized.success && recognized.data && recognized.data.length > 0) {
          category = recognized.data[0].category || category
          const categoryIndex = defaultCategoryIndex(category)
          this.setData({
            categoryIndex,
            'formData.category': CATEGORIES[categoryIndex],
          })
        }
      }

      const ref = await api.food.getShelfLifeReference(name, category)
      if (lookupSeq !== this.manualLookupSeq) {
        return
      }
      if (ref.success && ref.data.length > 0) {
        const shelfRef = ref.data[0]
        const profile = buildShelfProfile(shelfRef)
        const shelfLife = getShelfLifeByLocation(profile, this.data.formData.location)
        this.setData({
          'formData.shelf_life_days': shelfLife ? String(shelfLife) : this.data.formData.shelf_life_days,
          autoShelfLife: shelfLife || null,
          manualShelfProfile: profile,
          manualRecommendedLocation: shelfRef.recommended_location,
          manualStorageTip: shelfRef.storage_tip || '',
          storageSuggestion: `${LOCATION_LABELS[shelfRef.recommended_location] || '冷藏'} · ${shelfRef.storage_tip || '按当前保存方式自动计算保质期'}`,
        })
        this.openDecisionSheet('manual')
      } else {
        const fallbackLocation = getDefaultLocation(name, category)
        const fallbackShelfLife = getDefaultShelfLife(name, category) || (category === '肉类' ? 3 : '')
        this.setData({
          'formData.shelf_life_days': fallbackShelfLife ? String(fallbackShelfLife) : this.data.formData.shelf_life_days,
          autoShelfLife: fallbackShelfLife || null,
          manualShelfProfile: null,
          manualRecommendedLocation: fallbackLocation,
          manualStorageTip: getDefaultStorageTip(name, category, fallbackLocation),
          storageSuggestion: `${LOCATION_LABELS[fallbackLocation] || '冷藏'} · ${getDefaultStorageTip(name, category, fallbackLocation)}`,
        })
        if (fallbackShelfLife) {
          this.openDecisionSheet('manual')
        }
      }
    } catch (err) {
      console.error('查询手动保质期失败:', err)
    }
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
