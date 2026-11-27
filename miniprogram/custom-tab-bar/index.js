Component({
  data: {
    selected: 0,
    indicatorStyle: 'transform: translateX(0%);',
    list: [
      {
        pagePath: 'pages/index/index',
        text: '首页',
        symbol: '⌂',
        iconPath: '/images/home.png',
        selectedIconPath: '/images/home-active.png'
      },
      {
        pagePath: 'pages/add/add',
        text: '添加',
        symbol: '+',
        iconPath: '/images/add.png',
        selectedIconPath: '/images/add-active.png'
      },
      {
        pagePath: 'pages/settings/settings',
        text: '我的',
        symbol: '人',
        iconPath: '/images/user.png',
        selectedIconPath: '/images/user-active.png'
      }
    ]
  },

  lifetimes: {
    attached() {
      this.updateSelected()
    }
  },

  methods: {
    switchTab(event) {
      const { path, index } = event.currentTarget.dataset
      if (!path) {
        return
      }

      const app = getApp()
      if (app && typeof app.clearPendingNavigation === 'function') {
        app.clearPendingNavigation()
      }

      this.setData({
        selected: index,
        indicatorStyle: `transform: translateX(${index * 100}%);`
      })

      wx.switchTab({
        url: `/${path}`
      })
    },

    updateSelected(route) {
      const currentRoute = route || this.getCurrentRoute()
      const selected = this.data.list.findIndex((item) => item.pagePath === currentRoute)
      const nextIndex = selected >= 0 ? selected : 0

      this.setData({
        selected: nextIndex,
        indicatorStyle: `transform: translateX(${nextIndex * 100}%);`
      })
    },

    getCurrentRoute() {
      const pages = getCurrentPages()
      if (!pages || !pages.length) {
        return ''
      }

      return pages[pages.length - 1].route
    }
  }
})
