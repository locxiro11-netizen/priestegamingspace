/**
 * PriesteGamingSpace — UI Components v2
 * Daily Forge style: sidebar, academic cards, article detail
 */
const Components = (() => {

  const CAT_META = {
    home:        { label: '全部',       icon: '🏠', dot: '',         key: 'home' },
    gameUI:      { label: '游戏UI',     icon: '🎮', dot: 'ui',      key: 'gameUI' },
    screenshots: { label: '游戏截图',   icon: '📸', dot: 'screenshots', key: 'screenshots' },
    reflections: { label: '工作感悟',   icon: '📝', dot: 'reflections', key: 'reflections' }
  };

  let _itemCounter = 0;

  function _getDisplayNumber(category) {
    _itemCounter++;
    return _itemCounter;
  }

  // ========== Sidebar ==========

  function renderSidebar(currentTab, stats) {
    return `
      <button class="sidebar-publish" onclick="App.openCreateModal()">
        + 发布新内容
      </button>
      ${renderSidebarStats(stats)}
      ${renderSidebarNav(currentTab, stats)}
      <div class="sidebar-actions">
        <button class="sidebar-action-btn" onclick="App.handleExport()">
          <span>📤</span> 导出数据
        </button>
        <button class="sidebar-action-btn" onclick="document.getElementById('import-file').click()">
          <span>📥</span> 导入数据
        </button>
      </div>
    `;
  }

  function renderSidebarStats(stats) {
    return `
      <div class="sidebar-stats">
        <div class="sidebar-stats-title">内容统计</div>
        <div class="sidebar-stat-row">
          <span class="sidebar-stat-num">${stats.gameUI}</span>
          <span class="sidebar-stat-label">游戏UI</span>
        </div>
        <div class="sidebar-stat-row">
          <span class="sidebar-stat-num">${stats.screenshots}</span>
          <span class="sidebar-stat-label">游戏截图</span>
        </div>
        <div class="sidebar-stat-row">
          <span class="sidebar-stat-num">${stats.reflections}</span>
          <span class="sidebar-stat-label">工作感悟</span>
        </div>
        <div class="sidebar-stat-row" style="border-top:1px solid var(--border);margin-top:6px;padding-top:8px;">
          <span class="sidebar-stat-num">${stats.gameUI + stats.screenshots + stats.reflections}</span>
          <span class="sidebar-stat-label">总计</span>
        </div>
      </div>
    `;
  }

  function renderSidebarNav(currentTab, stats) {
    const tabs = ['home', 'gameUI', 'screenshots', 'reflections'];
    return `
      <nav class="sidebar-nav">
        ${tabs.map(tab => {
          const meta = CAT_META[tab];
          const count = tab === 'home'
            ? stats.gameUI + stats.screenshots + stats.reflections
            : stats[tab] || 0;
          return `
            <button class="sidebar-nav-item ${currentTab === tab ? 'active' : ''}"
              data-tab="${tab}">
              <span class="sidebar-nav-icon">${meta.icon}</span>
              ${meta.label}
              <span class="sidebar-nav-count">${count}</span>
            </button>
          `;
        }).join('')}
      </nav>
    `;
  }

  // ========== Search Bar ==========

  function renderSearchBar() {
    return `
      <div class="search-bar">
        <input type="text" id="search-input" placeholder="搜索标题、标签、游戏名称..."
          oninput="App.handleSearch(this.value)">
      </div>
    `;
  }

  // ========== Card (Academic Magazine Style) ==========

  function renderCard(item, category, index) {
    const meta = CAT_META[category] || CAT_META['home'];
    const tagHtml = item.tags?.map(t =>
      `<span class="card-tag">${escapeHtml(t)}</span>`
    ).join('') || '';

    return `
      <div class="card fade-in" data-id="${item.id}">
        <div class="card-meta">
          <span class="card-number">No.${String(index + 1).padStart(3, '0')}</span>
          <span class="card-cat-dot ${meta.dot}"></span>
          <span class="card-cat-label">${meta.label}</span>
          <span style="margin-left:auto">${item.date}</span>
        </div>

        ${item.image ? `
          <div class="card-image">
            <img src="${item.image}" alt="${escapeHtml(item.title)}" loading="lazy"
              onclick="App.openDetail('${category}', '${item.id}')">
          </div>
        ` : ''}

        <div class="card-body">
          <h3 class="card-title" onclick="App.openDetail('${category}', '${item.id}')">
            ${escapeHtml(item.title)}
          </h3>
          ${item.game ? `<span class="card-game">🎯 ${escapeHtml(item.game)}</span>` : ''}
          <p class="card-desc">${escapeHtml(truncate(item.desc || item.content || '', 200))}</p>
          ${tagHtml ? `<div class="card-tags">${tagHtml}</div>` : ''}
        </div>

        <div class="card-footer">
          <span class="card-date">${item.date}</span>
          <div class="card-actions">
            <button class="btn-like" data-action="like" data-id="${item.id}" data-cat="${category}">
              ♥ ${item.likes || 0}
            </button>
            <button class="btn-detail" onclick="App.openDetail('${category}', '${item.id}')">
              浏览详情 →
            </button>
            <button class="btn-delete" data-action="delete" data-id="${item.id}" data-cat="${category}">
              ✕
            </button>
          </div>
        </div>
      </div>
    `;
  }

  function renderCardGrid(items, category) {
    if (!items.length) {
      return `
        <div class="empty-state fade-in">
          <div class="empty-icon">—</div>
          <p>还没有内容</p>
          <p style="font-size:13px;color:var(--text-muted);margin-top:4px">点击侧边栏「+ 发布新内容」开始分享</p>
        </div>
      `;
    }
    return items.map((item, i) => renderCard(item, category, i)).join('');
  }

  // ========== Detail (Article Style) ==========

  function renderDetail(item, category) {
    const meta = CAT_META[category] || {};
    const tagHtml = item.tags?.map(t =>
      `<span class="card-tag">${escapeHtml(t)}</span>`
    ).join('') || '';

    return `
      <div class="modal-overlay" id="detail-modal">
        <div class="modal detail-modal" style="position:relative">
          <button class="modal-close" onclick="App.closeModal('detail-modal')">✕</button>

          ${item.image ? `
            <div class="detail-image">
              <img src="${item.image}" alt="${escapeHtml(item.title)}">
            </div>
          ` : ''}

          <div class="detail-meta">
            <span class="detail-cat-dot ${meta.dot}"></span>
            <span>${meta.label || ''}</span>
            <span style="margin-left:auto">${item.date}</span>
          </div>

          <h2 class="detail-title">${escapeHtml(item.title)}</h2>

          ${item.game ? `<div class="detail-game">🎯 ${escapeHtml(item.game)}</div>` : ''}

          <div class="detail-content">
            ${(item.content || item.desc || '').replace(/\n/g, '<br>')}
          </div>

          ${tagHtml ? `<div class="detail-tags">${tagHtml}</div>` : ''}

          <div class="detail-footer">
            <span style="color:var(--text-muted);font-size:13px">${item.date}</span>
            <button class="btn-like"
              onclick="Storage.toggleLike('${category}','${item.id}');App.refresh();App.closeModal('detail-modal')">
              ♥ ${item.likes || 0} 喜欢
            </button>
          </div>
        </div>
      </div>
    `;
  }

  // ========== Create Modal ==========

  function renderCreateModal(category) {
    const meta = CAT_META[category] || {};
    const isReflection = category === 'reflections';
    const isScreenshot = category === 'screenshots';

    return `
      <div class="modal-overlay" id="create-modal">
        <div class="modal create-modal">
          <div class="modal-header">
            <h2>发布${meta.label}</h2>
            <button class="modal-close" onclick="App.closeModal('create-modal')" style="position:static">✕</button>
          </div>
          <form id="create-form" onsubmit="App.handleCreate(event, '${category}')">
            <div class="form-group">
              <label>标题</label>
              <input type="text" name="title" required placeholder="输入标题..." maxlength="100">
            </div>
            ${isScreenshot ? `
              <div class="form-group">
                <label>游戏名称</label>
                <input type="text" name="game" placeholder="如：原神、崩坏：星穹铁道..." maxlength="50">
              </div>
            ` : ''}
            <div class="form-group">
              <label>${isReflection ? '正文' : '描述'}</label>
              ${isReflection ? `
                <textarea name="content" required placeholder="写下你的感悟..." rows="8" maxlength="5000"></textarea>
              ` : `
                <textarea name="desc" required placeholder="描述一下..." rows="4" maxlength="500"></textarea>
              `}
            </div>
            <div class="form-group">
              <label>标签（逗号分隔）</label>
              <input type="text" name="tags" placeholder="如：RPG, 界面设计, 心得" maxlength="200">
            </div>
            ${!isReflection ? `
              <div class="form-group">
                <label>上传图片</label>
                <div class="upload-area" id="upload-area">
                  <input type="file" name="image" accept="image/png,image/jpeg,image/webp,image/gif"
                    onchange="App.handleImagePreview(this)" style="display:none" id="image-input">
                  <div class="upload-placeholder" onclick="document.getElementById('image-input').click()">
                    <span class="upload-icon">📁</span>
                    <p>点击选择图片</p>
                    <small>支持 JPG / PNG / WebP / GIF，最大 10MB</small>
                  </div>
                  <div class="upload-preview" id="image-preview" style="display:none">
                    <img src="" alt="预览">
                    <button type="button" class="btn-remove-img" onclick="App.clearImagePreview()">✕</button>
                  </div>
                </div>
                <div class="upload-status" id="upload-status"></div>
              </div>
            ` : ''}
            <div class="form-actions">
              <button type="button" class="btn-cancel" onclick="App.closeModal('create-modal')">取消</button>
              <button type="submit" class="btn-submit" id="submit-btn">发布</button>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  // ========== Home Hero ==========

  function renderHomeHero() {
    return `
      <div class="home-hero fade-in">
        <h1 class="hero-title">PriesteGamingSpace</h1>
        <p class="hero-subtitle">游戏与生活的交集 · 分享不止于屏幕</p>
      </div>
    `;
  }

  // ========== Home Content (all categories mixed) ==========

  function renderHomeContent() {
    const allItems = Storage.getRecent(50);
    if (!allItems.length) {
      return `
        <div class="empty-state fade-in">
          <div class="empty-icon">—</div>
          <p>还没有内容</p>
          <p style="font-size:13px;color:var(--text-muted);margin-top:4px">点击左侧「+ 发布新内容」开始吧</p>
        </div>
      `;
    }
    return allItems.map((item, i) => renderCard(item, item.category, i)).join('');
  }

  // ========== Toast ==========

  function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} fade-in`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300); }, 2500);
  }

  // ========== Confirm Dialog ==========

  function showConfirm(message) {
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay';
      overlay.id = 'confirm-modal';
      overlay.innerHTML = `
        <div class="modal confirm-modal">
          <p>${message}</p>
          <div class="form-actions" style="justify-content:center">
            <button class="btn-cancel" id="confirm-no">取消</button>
            <button class="btn-submit" id="confirm-yes" style="background:var(--danger)">确认删除</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
      overlay.querySelector('#confirm-yes').onclick = () => { resolve(true);
        overlay.remove(); };
      overlay.querySelector('#confirm-no').onclick = () => { resolve(false);
        overlay.remove(); };
      overlay.onclick = (e) => { if (e.target === overlay) { resolve(false);
          overlay.remove(); } };
    });
  }

  // ========== Helpers ==========

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len) + '...' : str;
  }

  // ========== Public API ==========
  return {
    CAT_META,
    renderSidebar,
    renderSidebarStats,
    renderSidebarNav,
    renderSearchBar,
    renderCard,
    renderCardGrid,
    renderDetail,
    renderCreateModal,
    renderHomeHero,
    renderHomeContent,
    showToast,
    showConfirm,
    escapeHtml,
    truncate
  };
})();
