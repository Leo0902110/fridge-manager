const imageCache = Object.create(null)
const pendingCache = Object.create(null)

function isUnsafeHttpUrl(url) {
  return typeof url === 'string' && url.indexOf('http://') === 0
}

function isLocalTempUrl(url) {
  return typeof url === 'string' && (
    url.indexOf('wxfile://') === 0 ||
    url.indexOf('http://tmp/') === 0 ||
    url.indexOf('https://tmp/') === 0 ||
    url.indexOf('file://') === 0 ||
    url.indexOf('/') === 0 && url.indexOf('/uploads/') !== 0
  )
}

function getDisplayImageUrl(url) {
  if (!url || isUnsafeHttpUrl(url)) {
    return ''
  }
  return url
}

function getAppSafe() {
  try {
    return getApp()
  } catch (err) {
    return null
  }
}

function getOrigin(url) {
  const match = typeof url === 'string' ? url.match(/^https?:\/\/[^/]+/) : null
  return match ? match[0] : ''
}

function getUploadPath(url) {
  if (typeof url !== 'string') {
    return ''
  }
  const index = url.indexOf('/uploads/')
  return index >= 0 ? url.slice(index) : ''
}

function addUnique(list, value) {
  if (value && list.indexOf(value) === -1) {
    list.push(value)
  }
}

function buildCandidates(url) {
  const candidates = []
  const uploadPath = getUploadPath(url)

  if (uploadPath) {
    const app = getAppSafe()
    const globalData = app ? app.globalData || {} : {}
    const apiUrls = [globalData.API_BASE_URL].concat(globalData.API_BASE_URL_FALLBACKS || [])
    apiUrls.forEach((apiUrl) => {
      const origin = getOrigin(apiUrl)
      addUnique(candidates, origin ? origin + uploadPath : '')
    })
  }

  addUnique(candidates, url)
  return candidates
}

function downloadImage(url) {
  return new Promise((resolve) => {
    if (!url) {
      resolve('')
      return
    }
    wx.downloadFile({
      url,
      timeout: 12000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300 && res.tempFilePath) {
          resolve(res.tempFilePath)
          return
        }
        console.warn('图片下载状态异常:', url, res.statusCode)
        resolve('')
      },
      fail(err) {
        console.warn('图片下载失败:', url, err.errMsg || err)
        resolve('')
      },
    })
  })
}

async function resolveImageUrl(url) {
  if (!url) {
    return ''
  }
  if (isLocalTempUrl(url) || !isUnsafeHttpUrl(url)) {
    return url
  }
  if (imageCache[url]) {
    return imageCache[url]
  }
  if (pendingCache[url]) {
    return pendingCache[url]
  }

  pendingCache[url] = (async () => {
    const candidates = buildCandidates(url)
    const safeRemote = candidates.find(candidate => candidate && !isUnsafeHttpUrl(candidate))
    if (safeRemote) {
      imageCache[url] = safeRemote
      return safeRemote
    }

    for (let i = 0; i < candidates.length; i += 1) {
      const localPath = await downloadImage(candidates[i])
      if (localPath) {
        imageCache[url] = localPath
        return localPath
      }
    }
    return ''
  })()

  const resolved = await pendingCache[url]
  delete pendingCache[url]
  if (!resolved) {
    delete imageCache[url]
  }

  return resolved
}

function clearImageCache(url) {
  if (url) {
    delete imageCache[url]
    delete pendingCache[url]
    return
  }
  Object.keys(imageCache).forEach(key => delete imageCache[key])
  Object.keys(pendingCache).forEach(key => delete pendingCache[key])
}

module.exports = {
  getDisplayImageUrl,
  resolveImageUrl,
  isUnsafeHttpUrl,
  clearImageCache,
}