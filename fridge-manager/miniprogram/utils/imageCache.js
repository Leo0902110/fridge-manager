const imageCache = Object.create(null)

function isUnsafeHttpUrl(url) {
  return typeof url === 'string' && url.indexOf('http://') === 0
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
    wx.downloadFile({
      url,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300 && res.tempFilePath) {
          resolve(res.tempFilePath)
          return
        }
        resolve('')
      },
      fail() {
        resolve('')
      },
    })
  })
}

async function resolveImageUrl(url) {
  if (!url) {
    return ''
  }
  if (!isUnsafeHttpUrl(url)) {
    return url
  }
  if (imageCache[url]) {
    return imageCache[url]
  }

  imageCache[url] = (async () => {
    const candidates = buildCandidates(url)
    const safeRemote = candidates.find(candidate => candidate && !isUnsafeHttpUrl(candidate))
    if (safeRemote) {
      return safeRemote
    }

    for (let i = 0; i < candidates.length; i += 1) {
      const localPath = await downloadImage(candidates[i])
      if (localPath) {
        return localPath
      }
    }
    return ''
  })()

  return imageCache[url]
}

module.exports = {
  getDisplayImageUrl,
  resolveImageUrl,
  isUnsafeHttpUrl,
}