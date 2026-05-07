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
const FRESHNESS_LABELS = {
  fresh: '新鲜',
  normal: '一般',
  stale: '不太新鲜',
  spoiled: '疑似变质',
}
const QUICK_FOODS = [
  { name: '鸡蛋', category: '蛋类', location: 'fridge' },
  { name: '牛奶', category: '乳制品', location: 'fridge' },
  { name: '苹果', category: '水果', location: 'fridge' },
  { name: '青菜', category: '蔬菜', location: 'fridge' },
  { name: '猪肉', category: '肉类', location: 'freezer' },
  { name: '剩菜', category: '剩菜', location: 'fridge' },
]

function defaultCategoryIndex(category) {
  const index = CATEGORIES.indexOf(category)
  return index >= 0 ? index : CATEGORIES.length - 1
}

function normalizeFreshnessLevel(level) {
  const text = String(level || '').trim().toLowerCase()
  if (text === 'fresh' || text === '新鲜' || text === '较新鲜') return 'fresh'
  if (text === 'stale' || text === '不新鲜' || text === '欠新鲜') return 'stale'
  if (text === 'spoiled' || text === '变质' || text === '腐坏' || text === '发霉') return 'spoiled'
  return 'normal'
}

function normalizeFreshnessInfo(item) {
  const description = String((item && (item.freshness_description || item.freshness_reason || item.storage_tip)) || '')
  const score = Number(item && item.freshness_score)
  const severeKeywords = ['黑洞', '烂洞', '腐烂', '腐坏', '烂了', '发霉', '霉斑', '霉点', '软烂', '渗汁', '流汁', '大面积黑斑', '明显黑斑', '发黑凹陷']
  let level = normalizeFreshnessLevel(item && (item.freshness_level || item.freshness))
  const hasSevereSignal = severeKeywords.some(keyword => description.indexOf(keyword) >= 0)
  if (hasSevereSignal || (score && score < 20)) {
    level = 'spoiled'
  } else if (score >= 60) {
    level = 'fresh'
  } else if (score >= 40) {
    level = 'normal'
  } else if (score >= 20) {
    level = 'stale'
  } else if (level === 'spoiled') {
    level = 'stale'
  }
  const freshnessScore = level === 'spoiled' && (!score || score >= 20) ? 19 : (item && item.freshness_score) || ''
  const freshnessDescription = level === 'spoiled'
    ? (description || '疑似变质，不建议入库')
    : (item && (item.freshness_description || item.freshness_reason)) || ''
  return {
    level,
    score: freshnessScore,
    description: freshnessDescription,
  }
}

function getFreshnessLabel(level) {
  return FRESHNESS_LABELS[normalizeFreshnessLevel(level)] || FRESHNESS_LABELS.normal
}

function buildFreshnessNote(item) {
  if (!item || !item.freshness_level) {
    return ''
  }
  const label = getFreshnessLabel(item.freshness_level)
  const description = item.freshness_description || ''
  const score = item.freshness_score ? `，${item.freshness_score}分` : ''
  return `新鲜度：${label}${score}${description ? `（${description}）` : ''}`
}

function buildFoodNotes(item) {
  const notes = String((item && item.notes) || '').trim()
  const freshnessNote = buildFreshnessNote(item)
  return [notes, freshnessNote].filter(Boolean).join('；').slice(0, 100)
}

function buildSelectedItem(result, sourceIndex, imagePath) {
  const category = result.category || '其他'
  const shelfLife = result.shelf_life_days || getDefaultShelfLife(result.name, category)
  const hasAiShelfLife = !!result.shelf_life_days
  const recommendedLocation = result.recommended_location || getDefaultLocation(result.name, category)
  const displayImagePath = result.displayImagePath || result.crop_image_url || result.image_url || imagePath || ''
  const freshnessInfo = normalizeFreshnessInfo(result)
  const isSpoiled = freshnessInfo.level === 'spoiled'
  const item = {
    sourceIndex,
    name: result.name || '',
    category,
    categoryIndex: defaultCategoryIndex(category),
    confidence: result.confidence || 80,
    shelf_life_days: isSpoiled ? '1' : (shelfLife ? String(shelfLife) : ''),
    shelf_life_manual: false,
    shelf_life_source: hasAiShelfLife ? 'ai' : 'fallback',
    ai_shelf_life_days: hasAiShelfLife ? String(result.shelf_life_days) : '',
    ai_recommended_location: hasAiShelfLife ? recommendedLocation : '',
    shelfProfile: result.shelfProfile || null,
    recommended_location: isSpoiled ? 'fridge' : recommendedLocation,
    storage_tip: isSpoiled ? '疑似变质，建议丢弃' : (result.storage_tip || getDefaultStorageTip(result.name, category, recommendedLocation)),
    freshness_level: freshnessInfo.level,
    freshness_score: freshnessInfo.score,
    freshness_description: freshnessInfo.description,
    freshness_label: getFreshnessLabel(freshnessInfo.level),
    notes: '',
    imagePath: '',
    displayImagePath,
    cropStatus: imagePath ? '使用原图' : '无图片',
  }
  return {
    ...item,
    explain_text: buildShelfExplain(item, recommendedLocation),
  }
}

function buildShelfExplain(item, location) {
  if (!item) {
    return ''
  }

  const name = item.name || '该食材'
  const category = item.category || '食材'
  const currentLocation = location || item.location || item.recommended_location || item.ai_recommended_location || 'fridge'
  const locationText = LOCATION_LABELS[currentLocation] || '冷藏'
  const days = item.shelf_life_days || getItemShelfLifeForLocation(item, currentLocation) || ''
  const sourceText = item.shelf_life_manual
    ? '你手动调整后'
    : item.shelf_life_source === 'ai'
      ? 'AI 根据识别结果'
      : item.shelf_life_source === 'reference'
        ? '参考库根据常见保存数据'
        : '系统根据本地规则'
  const dayText = days ? `${locationText}约 ${days} 天` : `${locationText}需要再确认天数`
  const tip = item.storage_tip ? `，${item.storage_tip}` : ''
  return `${sourceText}判断：${name}属于${category}，当前按${dayText}管理${tip}。`
}

function buildManualSuggestionText(location, days, recommendedLocation, suffix = '') {
  const locationText = LOCATION_LABELS[location] || '冷藏'
  const dayText = days ? ` · ${days}天` : ''
  const recommendedText = recommendedLocation && recommendedLocation !== location
    ? `（更推荐${LOCATION_LABELS[recommendedLocation] || '冷藏'}）`
    : ''
  return `${locationText}${dayText}${recommendedText}${suffix}`
}

function getDefaultShelfLife(name, category) {
  const text = `${name || ''}${category || ''}`
  if (text.indexOf('罐头') >= 0 || text.indexOf('密封') >= 0) {
    return text.indexOf('开封') >= 0 ? 3 : 180
  }
  if (text.indexOf('菠萝') >= 0 || text.indexOf('凤梨') >= 0) {
    return 5
  }
  if (category === '熟食' || category === '剩菜' || COOKED_KEYWORDS.some(keyword => text.indexOf(keyword) >= 0)) {
    return 2
  }
  return ''
}

function getDefaultShelfLifeForLocation(name, category, location) {
  const text = `${name || ''}${category || ''}`
  const isOpened = ['开封', '已开', '打开', '切开', '切块', '剩余'].some(keyword => text.indexOf(keyword) >= 0)
  const dryFoodKeywords = ['饼干', '方便面', '泡面', '挂面', '米', '面粉', '麦片', '燕麦', '坚果', '糖果', '巧克力', '零食', '茶叶', '咖啡', '饮料', '调味', '酱油', '醋']
  const rootKeywords = ['土豆', '洋葱', '大蒜', '蒜', '姜', '南瓜', '红薯', '地瓜', '山药', '芋头']
  const roomFruitKeywords = ['香蕉', '苹果', '橙', '橘', '柑', '梨', '柚子', '柠檬', '牛油果', '猕猴桃', '芒果']

  if (location === 'room') {
    if ((text.indexOf('罐头') >= 0 || text.indexOf('密封') >= 0) && !isOpened) return 180
    if (dryFoodKeywords.some(keyword => text.indexOf(keyword) >= 0) && !isOpened) return 90
    if (rootKeywords.some(keyword => text.indexOf(keyword) >= 0)) return 14
    if (roomFruitKeywords.some(keyword => text.indexOf(keyword) >= 0) && !isOpened) return text.indexOf('香蕉') >= 0 ? 3 : 7
    if (text.indexOf('面包') >= 0 || text.indexOf('吐司') >= 0) return 3
    if (text.indexOf('鸡蛋') >= 0 || category === '蛋类') return 7
    if (text.indexOf('菠萝') >= 0 || text.indexOf('凤梨') >= 0) return isOpened ? 1 : 2
    if (category === '水果') return isOpened ? 1 : 2
    if (category === '蔬菜') return 1
    if (category === '肉类' || category === '海鲜' || category === '乳制品' || category === '豆制品' || category === '熟食' || category === '剩菜' || COOKED_KEYWORDS.some(keyword => text.indexOf(keyword) >= 0)) return 1
    return ''
  }

  if (location === 'freezer') {
    if (category === '肉类' || category === '海鲜') return 90
    if (category === '熟食' || category === '剩菜') return 14
    if (category === '水果' || category === '蔬菜') return 30
  }

  if (location === 'fridge') {
    return getDefaultShelfLife(name, category)
  }

  return ''
}

function getDefaultLocation(name, category) {
  const text = `${name || ''}${category || ''}`
  if ((text.indexOf('罐头') >= 0 || text.indexOf('密封') >= 0) && text.indexOf('开封') < 0) {
    return 'room'
  }
  if (['饼干', '方便面', '泡面', '挂面', '米', '面粉', '麦片', '燕麦', '坚果', '糖果', '巧克力', '零食', '土豆', '洋葱', '大蒜', '姜', '南瓜', '红薯', '山药', '香蕉', '面包', '吐司'].some(keyword => text.indexOf(keyword) >= 0)) {
    return 'room'
  }
  if (category === '肉类' || category === '海鲜') {
    return 'freezer'
  }
  return 'fridge'
}

function getDefaultStorageTip(name, category, location) {
  const text = `${name || ''}${category || ''}`
  if (text.indexOf('罐头') >= 0 || text.indexOf('密封') >= 0) {
    return text.indexOf('开封') >= 0 ? '开封后冷藏尽快吃' : '未开封阴凉保存'
  }
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

function getItemShelfLifeForLocation(item, location) {
  if (item && item.shelf_life_manual && item.shelf_life_days) {
    return item.shelf_life_days
  }
  if (item && item.shelf_life_source === 'ai') {
    const aiLocation = item.ai_recommended_location || item.recommended_location
    if (location === aiLocation && (item.ai_shelf_life_days || item.shelf_life_days)) {
      return item.ai_shelf_life_days || item.shelf_life_days
    }
    return getShelfLifeByLocation(item.shelfProfile, location) || getDefaultShelfLifeForLocation(item.name, item.category, location) || ''
  }
  return getShelfLifeByLocation(item && item.shelfProfile, location) || getDefaultShelfLifeForLocation(item && item.name, item && item.category, location) || (item && item.shelf_life_days) || ''
}

function buildLocationDays(item) {
  return {
    fridge: getItemShelfLifeForLocation(item, 'fridge'),
    freezer: getItemShelfLifeForLocation(item, 'freezer'),
    room: getItemShelfLifeForLocation(item, 'room'),
  }
}

function formatLocationDayLabel(days, location, item) {
  if (days) {
    return `${days}天`
  }
  const text = `${(item && item.name) || ''}${(item && item.category) || ''}`
  if (location === 'room' && (item && (item.category === '肉类' || item.category === '海鲜' || item.category === '乳制品' || item.category === '豆制品' || item.category === '熟食' || item.category === '剩菜' || COOKED_KEYWORDS.some(keyword => text.indexOf(keyword) >= 0)))) {
    return '不建议'
  }
  return '待确认'
}

function buildLocationDayLabels(locationDays, item) {
  const days = locationDays || {}
  return {
    fridge: formatLocationDayLabel(days.fridge, 'fridge', item),
    freezer: formatLocationDayLabel(days.freezer, 'freezer', item),
    room: formatLocationDayLabel(days.room, 'room', item),
  }
}

function applyLocationShelfLifeToItems(items, location) {
  return items.map((item) => {
    if (item.shelf_life_manual) {
      return {
        ...item,
        explain_text: buildShelfExplain(item, location || item.location || item.recommended_location),
      }
    }
    const shelfLife = getItemShelfLifeForLocation(item, location)
    const nextItem = shelfLife ? { ...item, shelf_life_days: String(shelfLife) } : item
    return {
      ...nextItem,
      explain_text: buildShelfExplain(nextItem, location || nextItem.location || nextItem.recommended_location),
    }
  })
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
    quickFoods: QUICK_FOODS,

    imagePath: '',
    recognitionError: '',
    recognitionResults: [],
    wholeItem: null,
    entryMode: 'split',
    modeReason: '',
    selectedItems: [],
    selectedCount: 0,
    editorVisible: false,
    decisionVisible: false,
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
    manualExplainText: '',
    manualLookupLoading: false,
    manualSuggestionReady: false,
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

  onUnload() {
    clearTimeout(this.manualLookupTimer)
  },

  noop() {},

  resetAddPage() {
    if (this.data.recognizing || this.data.submitting) {
      return
    }

    clearTimeout(this.manualLookupTimer)
    this.manualLookupSeq = (this.manualLookupSeq || 0) + 1
    this.setData({
      imagePath: '',
      recognitionError: '',
      recognitionResults: [],
      wholeItem: null,
      entryMode: 'split',
      modeReason: '',
      selectedItems: [],
      selectedCount: 0,
      editorVisible: false,
      decisionVisible: false,
      decisionSource: '',
      decisionIndex: -1,
      decisionItem: null,
      editingIndex: -1,
      editDraft: null,
      categoryIndex: CATEGORIES.length - 1,
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
      manualExplainText: '',
      manualLookupLoading: false,
      manualSuggestionReady: false,
    })
  },

  async chooseImage() {
    if (this.data.recognizing || this.data.submitting) {
      return
    }

    const handleImagePath = (imagePath) => {
      if (imagePath) {
        this.recognizeSelectedImage(imagePath)
      }
    }
    const handleChooseFail = (err) => {
      const message = err && (err.errMsg || err.message || String(err))
      if (message && message.indexOf('cancel') >= 0) {
        return
      }
      console.error('选择图片失败:', err)
      wx.showToast({
        title: '无法打开相机，请检查权限或改用相册',
        icon: 'none',
      })
    }
    const fallbackChooseImage = () => {
      wx.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: ['camera', 'album'],
        success: (res) => {
          handleImagePath(res.tempFilePaths && res.tempFilePaths[0])
        },
        fail: handleChooseFail,
      })
    }

    if (!wx.chooseMedia) {
      fallbackChooseImage()
      return
    }

    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      camera: 'back',
      success: async (res) => {
        const tempFilePath = res.tempFiles[0].tempFilePath
        handleImagePath(tempFilePath)
      },
      fail: (err) => {
        const message = err && (err.errMsg || err.message || String(err))
        if (message && message.indexOf('cancel') >= 0) {
          return
        }
        fallbackChooseImage()
      },
    })
  },

  async retryRecognition() {
    if (!this.data.imagePath || this.data.recognizing || this.data.submitting) {
      return
    }
    this.recognizeSelectedImage(this.data.imagePath)
  },

  async recognizeSelectedImage(imagePath) {
    this.setData({
      imagePath,
      recognitionError: '',
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
      const result = await api.recognition.recognizeImage(imagePath)
      const results = (result.success && result.data ? result.data : []).map((item, index) => {
        const freshnessInfo = normalizeFreshnessInfo(item)
        return {
          ...item,
          freshness_level: freshnessInfo.level,
          freshness_score: freshnessInfo.score,
          freshness_description: freshnessInfo.description,
          freshness_label: getFreshnessLabel(freshnessInfo.level),
          selected: result.mode !== 'whole',
          sourceIndex: index,
          displayImagePath: item.crop_image_url || item.image_url || imagePath,
        }
      })
      const wholeItem = result.whole_food ? buildSelectedItem(result.whole_food, -1, imagePath) : null
      const shouldUseWhole = result.mode === 'whole' && wholeItem
      const selectedItems = shouldUseWhole
        ? [wholeItem]
        : results.map((item, index) => buildSelectedItem(item, index, imagePath))

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
      this.setData({
        recognizing: false,
        recognitionError: errorMessage,
      })
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
    if (item.shelf_life_manual) {
      return
    }

    const hasAiShelfLife = item.shelf_life_source === 'ai' && !!item.shelf_life_days

    if (hasAiShelfLife) {
      return
    }

    const defaultShelfLife = getDefaultShelfLife(item.name, item.category)
    if (!item.shelf_life_days && defaultShelfLife) {
      item.shelf_life_days = String(defaultShelfLife)
      const nextItem = { ...item, shelf_life_days: String(defaultShelfLife), shelf_life_source: 'fallback' }
      this.setData({
        [`selectedItems[${index}].shelf_life_days`]: String(defaultShelfLife),
        [`selectedItems[${index}].shelf_life_source`]: 'fallback',
        [`selectedItems[${index}].explain_text`]: buildShelfExplain(nextItem, item.recommended_location || this.data.formData.location),
      })
    }

    try {
      const ref = await api.food.getShelfLifeReference(item.name, item.category)
      if (ref.success && ref.data.length > 0) {
        const shelfRef = ref.data[0]
        const profile = buildShelfProfile(shelfRef)
        const location = item.recommended_location || this.data.formData.location
        const shelfLife = getShelfLifeByLocation(profile, location) || item.shelf_life_days || 7
        const nextItem = {
          ...item,
          shelf_life_days: String(shelfLife),
          shelf_life_source: 'reference',
          shelfProfile: profile,
          recommended_location: shelfRef.recommended_location || item.recommended_location,
          storage_tip: shelfRef.storage_tip || item.storage_tip,
        }
        this.setData({
          [`selectedItems[${index}].shelf_life_days`]: String(shelfLife),
          [`selectedItems[${index}].shelf_life_source`]: 'reference',
          [`selectedItems[${index}].shelfProfile`]: profile,
          [`selectedItems[${index}].recommended_location`]: shelfRef.recommended_location || item.recommended_location,
          [`selectedItems[${index}].storage_tip`]: shelfRef.storage_tip || item.storage_tip,
          [`selectedItems[${index}].explain_text`]: buildShelfExplain(nextItem, location),
        })
      } else if (!item.shelf_life_days) {
        const nextItem = { ...item, shelf_life_days: '7', shelf_life_source: 'fallback' }
        this.setData({
          [`selectedItems[${index}].shelf_life_days`]: '7',
          [`selectedItems[${index}].shelf_life_source`]: 'fallback',
          [`selectedItems[${index}].explain_text`]: buildShelfExplain(nextItem, item.recommended_location || this.data.formData.location),
        })
      }
    } catch (err) {
      console.error('查询保质期失败:', err)
      if (!item.shelf_life_days) {
        const nextItem = { ...item, shelf_life_days: '7', shelf_life_source: 'fallback' }
        this.setData({
          [`selectedItems[${index}].shelf_life_days`]: '7',
          [`selectedItems[${index}].shelf_life_source`]: 'fallback',
          [`selectedItems[${index}].explain_text`]: buildShelfExplain(nextItem, item.recommended_location || this.data.formData.location),
        })
      }
    }
  },

  buildDecisionItem(item, source) {
    const profile = item.shelfProfile || (source === 'manual' ? this.data.manualShelfProfile : null) || {}
    const location = source === 'manual'
      ? this.data.formData.location
      : (item.recommended_location || this.data.formData.location || 'fridge')
    const shelfLife = source === 'manual'
      ? getShelfLifeByLocation(profile, location) || item.shelf_life_days || this.data.formData.shelf_life_days
      : getItemShelfLifeForLocation({ ...item, shelfProfile: profile }, location) || this.data.formData.shelf_life_days
    const locationDays = buildLocationDays({ ...item, shelfProfile: profile, shelf_life_days: shelfLife ? String(shelfLife) : item.shelf_life_days })
    return {
      ...item,
      source,
      shelfProfile: profile,
      location,
      shelf_life_days: shelfLife ? String(shelfLife) : '',
      locationDays,
      locationDayLabels: buildLocationDayLabels(locationDays, item),
      expiryPreview: shelfLife ? calcExpiryDate(shelfLife) : '',
      recommended_location: item.recommended_location || this.data.manualRecommendedLocation || getDefaultLocation(item.name, item.category),
      storage_tip: item.storage_tip || this.data.manualStorageTip || getDefaultStorageTip(item.name, item.category, location),
      explain_text: buildShelfExplain({ ...item, shelfProfile: profile, shelf_life_days: shelfLife ? String(shelfLife) : item.shelf_life_days }, location),
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
      decisionSource: source,
      decisionIndex: index,
      decisionItem: this.buildDecisionItem(item, source),
    })
  },

  closeDecisionSheet() {
    this.setData({
      decisionVisible: false,
      decisionSource: '',
      decisionIndex: -1,
      decisionItem: null,
    })
  },

  selectDecisionLocation(e) {
    const location = e.currentTarget.dataset.location
    const item = this.data.decisionItem
    if (!item) {
      return
    }

    const shelfLife = getItemShelfLifeForLocation(item, location)
    const locationDays = buildLocationDays({ ...item, location, shelf_life_days: shelfLife ? String(shelfLife) : item.shelf_life_days })
    this.setData({
      'decisionItem.location': location,
      'decisionItem.shelf_life_days': shelfLife ? String(shelfLife) : '',
      'decisionItem.locationDays': locationDays,
      'decisionItem.locationDayLabels': buildLocationDayLabels(locationDays, item),
      'decisionItem.expiryPreview': shelfLife ? calcExpiryDate(shelfLife) : '',
      'decisionItem.explain_text': buildShelfExplain({ ...item, shelf_life_days: shelfLife ? String(shelfLife) : item.shelf_life_days }, location),
    })
  },

  onRecognitionImageError(e) {
    const index = Number(e.currentTarget.dataset.index)
    if (Number.isNaN(index)) return
    this.setData({
      [`recognitionResults[${index}].displayImagePath`]: '',
    })
  },

  onSelectedImageError(e) {
    const index = Number(e.currentTarget.dataset.index)
    if (Number.isNaN(index)) return
    this.setData({
      [`selectedItems[${index}].displayImagePath`]: '',
      [`selectedItems[${index}].imagePath`]: '',
    })
  },

  onEditImageError() {
    this.setData({
      'editDraft.displayImagePath': '',
      'editDraft.imagePath': '',
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
        manualExplainText: buildShelfExplain(item, item.location),
      })
    } else if (this.data.decisionIndex >= 0) {
      const selectedItems = this.data.selectedItems.slice()
      selectedItems[this.data.decisionIndex] = {
        ...selectedItems[this.data.decisionIndex],
        shelf_life_days: item.shelf_life_days,
        recommended_location: item.recommended_location,
        storage_tip: item.storage_tip,
        shelfProfile: item.shelfProfile,
        shelf_life_manual: !!item.shelf_life_manual,
        explain_text: buildShelfExplain(item, item.location),
      }
      this.setData({
        selectedItems: applyLocationShelfLifeToItems(selectedItems, item.location),
        'formData.location': item.location,
      })
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
          [`selectedItems[${index}].displayImagePath`]: res.tempFilePath,
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
          'editDraft.displayImagePath': res.tempFilePath,
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

    const shelfLifeDays = String(editDraft.shelf_life_days || '').replace(/\D/g, '')
    const originalItem = this.data.selectedItems[editingIndex] || {}
    const isManualShelfLife = !!editDraft.shelf_life_manual || shelfLifeDays !== String(originalItem.shelf_life_days || '')

    if (!editDraft.name.trim()) {
      wx.showToast({ title: '请输入食物名称', icon: 'none' })
      return
    }

    if (!shelfLifeDays) {
      wx.showToast({ title: '请输入保质期', icon: 'none' })
      return
    }

    const selectedItems = this.data.selectedItems.slice()
    const savedItem = {
        ...editDraft,
        name: editDraft.name.trim(),
        shelf_life_days: shelfLifeDays,
        shelf_life_manual: isManualShelfLife,
        shelf_life_source: isManualShelfLife ? 'manual' : (editDraft.shelf_life_source || originalItem.shelf_life_source || 'fallback'),
        notes: (editDraft.notes || '').trim(),
      }
    selectedItems[editingIndex] = savedItem

    const updates = {
      selectedItems,
      editorVisible: false,
      editingIndex: -1,
      editDraft: null,
    }
    if (this.data.decisionVisible && this.data.decisionIndex === editingIndex) {
      const decisionItem = this.buildDecisionItem(savedItem, this.data.decisionSource || 'item')
      updates.decisionItem = decisionItem
    }
    if (savedItem.sourceIndex === -1 && this.data.entryMode === 'whole') {
      updates.wholeItem = { ...savedItem }
    }

    this.setData(updates)
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

  scheduleManualShelfLifeLookup(value) {
    clearTimeout(this.manualLookupTimer)
    if (!value.trim()) {
      this.setData({
        autoShelfLife: null,
        storageSuggestion: '',
        manualShelfProfile: null,
        manualRecommendedLocation: '',
        manualStorageTip: '',
        manualExplainText: '',
        manualLookupLoading: false,
        manualSuggestionReady: false,
      })
      return
    }

    this.setData({ manualLookupLoading: true })
    this.manualLookupTimer = setTimeout(() => {
      this.fillManualShelfLife()
    }, 650)
  },

  applyLocationShelfLife(location) {
    this.setData({
      selectedItems: applyLocationShelfLifeToItems(this.data.selectedItems, location),
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
    if (field === 'name' && value.trim()) {
      this.scheduleManualShelfLifeLookup(value)
    } else if (field === 'name') {
      this.scheduleManualShelfLifeLookup(value)
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
    const value = field === 'shelf_life_days'
      ? String(e.detail.value || '').replace(/\D/g, '')
      : e.detail.value
    const updates = {
      [`editDraft.${field}`]: value,
    }
    if (field === 'shelf_life_days') {
      updates['editDraft.shelf_life_manual'] = true
    }
    this.setData({
      ...updates,
    })
    if (field === 'shelf_life_days') {
      return value
    }
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

  fillQuickFood(e) {
    if (this.data.submitting || this.data.recognizing) {
      return
    }

    const index = Number(e.currentTarget.dataset.index)
    const item = this.data.quickFoods[index]
    if (!item) {
      return
    }

    const categoryIndex = defaultCategoryIndex(item.category)
    this.setData({
      categoryIndex,
      'formData.name': item.name,
      'formData.category': item.category,
      'formData.location': item.location,
    })
    this.fillManualShelfLife()
  },

  applyManualSuggestion() {
    const name = this.data.formData.name.trim()
    if (!name || !this.data.manualSuggestionReady) {
      return
    }

    const location = this.data.manualRecommendedLocation || this.data.formData.location
    const shelfLife = getShelfLifeByLocation(this.data.manualShelfProfile, location)
      || this.data.formData.shelf_life_days
      || getDefaultShelfLife(name, this.data.formData.category)
      || 7

    this.setData({
      'formData.location': location,
      'formData.shelf_life_days': String(shelfLife),
      storageSuggestion: `${LOCATION_LABELS[location] || '冷藏'} · ${this.data.manualStorageTip || '按推荐方式保存'}`,
      manualExplainText: buildShelfExplain({
        name,
        category: this.data.formData.category || CATEGORIES[this.data.categoryIndex] || '其他',
        shelf_life_days: String(shelfLife),
        shelf_life_source: this.data.manualShelfProfile ? 'reference' : 'fallback',
        storage_tip: this.data.manualStorageTip || '按推荐方式保存',
        recommended_location: location,
        shelfProfile: this.data.manualShelfProfile,
      }, location),
    })
    wx.showToast({ title: '已应用推荐', icon: 'success' })
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

  getFreshnessLabel(level) {
    return getFreshnessLabel(level)
  },

  async fillManualShelfLife() {
    const name = this.data.formData.name.trim()
    if (!name) {
      return
    }
    const lookupSeq = (this.manualLookupSeq || 0) + 1
    this.manualLookupSeq = lookupSeq
    this.setData({ manualLookupLoading: true })

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
        const currentLocation = this.data.formData.location
        const shelfLife = getShelfLifeByLocation(profile, currentLocation)
        const recommendedLocation = shelfRef.recommended_location || currentLocation
        this.setData({
          'formData.shelf_life_days': shelfLife ? String(shelfLife) : this.data.formData.shelf_life_days,
          autoShelfLife: shelfLife || null,
          manualShelfProfile: profile,
          manualRecommendedLocation: recommendedLocation,
          manualStorageTip: shelfRef.storage_tip || '',
          storageSuggestion: buildManualSuggestionText(currentLocation, shelfLife || '--', recommendedLocation),
          manualExplainText: buildShelfExplain({
            name,
            category,
            shelf_life_days: shelfLife ? String(shelfLife) : this.data.formData.shelf_life_days,
            shelf_life_source: 'reference',
            shelfProfile: profile,
            recommended_location: recommendedLocation,
            storage_tip: shelfRef.storage_tip || '',
          }, currentLocation),
          manualLookupLoading: false,
          manualSuggestionReady: true,
        })
      } else {
        const currentLocation = this.data.formData.location
        const fallbackLocation = getDefaultLocation(name, category)
        const fallbackShelfLife = getDefaultShelfLifeForLocation(name, category, currentLocation)
          || getDefaultShelfLife(name, category)
          || (category === '肉类' ? 3 : '')
        this.setData({
          'formData.shelf_life_days': fallbackShelfLife ? String(fallbackShelfLife) : this.data.formData.shelf_life_days,
          autoShelfLife: fallbackShelfLife || null,
          manualShelfProfile: null,
          manualRecommendedLocation: fallbackLocation,
          manualStorageTip: getDefaultStorageTip(name, category, fallbackLocation),
          storageSuggestion: buildManualSuggestionText(currentLocation, fallbackShelfLife, fallbackLocation),
          manualExplainText: buildShelfExplain({
            name,
            category,
            shelf_life_days: fallbackShelfLife ? String(fallbackShelfLife) : this.data.formData.shelf_life_days,
            shelf_life_source: 'fallback',
            recommended_location: fallbackLocation,
            storage_tip: getDefaultStorageTip(name, category, fallbackLocation),
          }, currentLocation),
          manualLookupLoading: false,
          manualSuggestionReady: true,
        })
      }
    } catch (err) {
      console.warn('查询手动保质期失败，使用本地兜底:', err)
      if (lookupSeq === this.manualLookupSeq) {
        const category = this.data.formData.category || CATEGORIES[this.data.categoryIndex] || '其他'
        const currentLocation = this.data.formData.location
        const fallbackLocation = getDefaultLocation(name, category)
        const fallbackShelfLife = getDefaultShelfLifeForLocation(name, category, currentLocation)
          || getDefaultShelfLife(name, category)
          || (category === '肉类' ? 3 : '')
        this.setData({
          'formData.shelf_life_days': fallbackShelfLife ? String(fallbackShelfLife) : this.data.formData.shelf_life_days,
          autoShelfLife: fallbackShelfLife || null,
          manualShelfProfile: null,
          manualRecommendedLocation: fallbackLocation,
          manualStorageTip: getDefaultStorageTip(name, category, fallbackLocation),
          storageSuggestion: buildManualSuggestionText(currentLocation, fallbackShelfLife, fallbackLocation, '（本地估算）'),
          manualExplainText: buildShelfExplain({
            name,
            category,
            shelf_life_days: fallbackShelfLife ? String(fallbackShelfLife) : this.data.formData.shelf_life_days,
            shelf_life_source: 'fallback',
            recommended_location: fallbackLocation,
            storage_tip: getDefaultStorageTip(name, category, fallbackLocation),
          }, currentLocation),
          manualLookupLoading: false,
          manualSuggestionReady: !!fallbackShelfLife,
        })
      }
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
            notes: buildFoodNotes(item),
          })
        }
      } else {
        wx.showLoading({ title: this.data.imagePath ? '上传图片...' : '保存中...' })
        const imageUrl = this.data.imagePath ? await this.uploadItemImage({ imagePath: this.data.imagePath }) : ''
        wx.showLoading({ title: '保存中...' })
        const res = await api.food.create({
          name: this.data.formData.name.trim(),
          category: this.data.formData.category || '其他',
          image_url: imageUrl,
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

      if (typeof app.markFoodListDirty === 'function') {
        app.markFoodListDirty()
      }
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
