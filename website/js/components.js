/**
 * PriesteGamingSpace v3 — UI Components
 * Daily Forge style: stats bar, nav tabs, date selector, calendar, sign-in, bookmarks
 */
const Components = (() => {

  const CAT_META = {
    home:        { label: '全部',       icon: '', key: 'home' },
    gameUI:      { label: '游戏UI分享', icon: '🎮', key: 'gameUI' },
    screenshots: { label: '游戏截图',   icon: '📸', key: 'screenshots' },
    reflections: { label: '工作感悟',   icon: '📝', key: 'reflections' },
    life:        { label: '生活与自然', icon: '🌿', key: 'life' }
  };

  const NAV_TABS = [
    { id: 'home',        label: '今日精选' },
    { id: 'gameUI',      label: '游戏UI' },
    { id: 'screenshots', label: '游戏截图' },
    { id: 'reflections', label: '工作感悟' },
    { id: 'life',        label: '🌿 生活与自然' },
    { id: 'archive',     label: '归档' }
  ];

  const FILTER_PILLS = [
    { id: 'all',         label: '全部' },
    { id: 'gameUI',      label: '游戏UI' },
    { id: 'screenshots', label: '游戏截图' },
    { id: 'reflections', label: '工作感悟' },
    { id: 'life',        label: '生活与自然' }
  ];

  // ========== Stats Bar ==========

  function renderStatsBar(stats, totalDays) {
    const items = [
      { num: stats.gameUI, label: '游戏UI', icon: '🎮' },
      { num: stats.screenshots, label: '游戏截图', icon: '📸' },
      { num: stats.reflections, label: '工作感悟', icon: '📝' },
      { num: stats.life, label: '生活与自然', icon: '🌿' },
      { num: totalDays, label: '累计天数', icon: '📅' }
    ];
    return items.map(s => `
      <div class="stat-card fade-in">
        <span class="stat-icon">${s.icon}</span>
        <div class="stat-info">
          <span class="stat-num">${s.num}</span>
          <span class="stat-label">${s.label}</span>
        </div>
      </div>
    `).join('');
  }

  // ========== Nav Tabs ==========

  function renderNavTabs(currentTab) {
    return NAV_TABS.map(tab => `
      <button class="nav-tab ${currentTab === tab.id ? 'active' : ''}"
        data-tab="${tab.id}">${tab.label}</button>
    `).join('');
  }

  // ========== Sub Bar (date + filter pills + bookmarks) ==========

  function renderSubBar(currentTab, currentDateIndex, totalDates, dates, activeFilter) {
    const currentDate = dates[currentDateIndex] || '—';
    const dateDisplay = formatDateDisplay(currentDate);
    const canPrev = currentDateIndex < totalDates - 1;
    const canNext = currentDateIndex > 0;

    return `
      <div class="date-selector">
        <button class="date-arrow" onclick="App.prevDate()" ${canPrev ? '' : 'disabled'}>←</button>
        <span class="date-text">
          <span class="day-num">Day ${String(totalDates - currentDateIndex).padStart(3,'0')}</span>
          / ${totalDates}
        </span>
        <button class="date-arrow" onclick="App.nextDate()" ${canNext ? '' : 'disabled'}>→</button>
        <button class="cal-btn" onclick="App.openCalendar()">📅</button>
      </div>

      <div class="filter-pills">
        ${FILTER_PILLS.map(p => `
          <button class="filter-pill ${activeFilter === p.id ? 'active' : ''}"
            data-filter="${p.id}" onclick="App.setFilter('${p.id}')">${p.label}</button>
        `).join('')}
        <button class="filter-pill" onclick="App.openBookmarks()">📌 收藏</button>
        <button class="filter-pill admin-only" onclick="App.openCreateModal()" style="background:var(--accent);color:#FFF;border-color:var(--accent)">📝 发布</button>
      </div>
    `;
  }

  // ========== Day Title ==========

  function renderDayTitle(dateIndex, totalDates, currentDate) {
    if (!currentDate || currentDate === '—') return '';
    const dateDisplay = formatDateDisplay(currentDate);
    return `
      <div class="day-title fade-in">
        Day <span class="day-num">_${String(totalDates - dateIndex).padStart(3,'0')}_</span>
        <span class="day-date">${dateDisplay}</span>
      </div>
    `;
  }

  // ========== Section Header ==========

  function renderSectionHeader(num, title, sub) {
    return `
      <div class="section-header fade-in">
        <span class="sec-num">${String(num).padStart(2,'0')}</span>
        <span class="sec-title">${title}</span>
        ${sub ? `<span class="sec-sub">${sub}</span>` : ''}
      </div>
    `;
  }

  // ========== Card (Academic Magazine) ==========

  function renderCard(item, index, showBookmark) {
    const tagHtml = item.tags?.map(t =>
      `<span class="card-tag">${escapeHtml(t)}</span>`
    ).join('') || '';
    const isBm = showBookmark && Storage.isBookmarked(item.id);

    return `
      <div class="card fade-in" data-id="${item.id}">
        ${item.image ? `
          <div class="card-image">
            <img src="${item.image}" alt="${escapeHtml(item.title)}" loading="lazy"
              onclick="App.openDetail('${item.category}', '${item.id}')">
          </div>
        ` : ''}
        <div class="card-body">
          <h3 class="card-title" onclick="App.openDetail('${item.category}', '${item.id}')">
            ${escapeHtml(item.title)}
          </h3>
          ${item.game ? `<span class="card-game">🎯 ${escapeHtml(item.game)}</span>` : ''}
          <p class="card-desc">${escapeHtml(truncate(item.desc || item.content || '', 250))}</p>
          ${tagHtml ? `<div class="card-tags">${tagHtml}</div>` : ''}
        </div>
        <div class="card-footer">
          <span class="card-date">${item.date}</span>
          <div class="card-actions">
            <button class="btn-like" data-action="like" data-id="${item.id}" data-cat="${item.category}">
              ♥ ${item.likes || 0}
            </button>
            <button class="btn-bookmark ${isBm ? 'bookmarked' : ''}"
              data-action="bookmark" data-id="${item.id}" data-cat="${item.category}">
              ${isBm ? '★' : '☆'} 收藏
            </button>
            <button class="btn-detail" onclick="App.openDetail('${item.category}', '${item.id}')">
              深入阅读 →
            </button>
            <button class="btn-delete admin-only" data-action="delete" data-id="${item.id}" data-cat="${item.category}">✕</button>
          </div>
        </div>
      </div>
    `;
  }

  // ========== Main Content Renderer ==========

  function renderContentByDate(dateData, activeFilter) {
    if (!dateData) return renderEmpty();

    const sections = [
      { cat: 'gameUI', num: 1, title: '游戏UI分享', sub: 'Game UI Sharing' },
      { cat: 'screenshots', num: 2, title: '游戏截图', sub: 'Game Screenshots' },
      { cat: 'reflections', num: 3, title: '工作感悟', sub: 'Work Reflections' },
      { cat: 'life', num: 4, title: '生活与自然', sub: 'Life & Nature' }
    ];

    let html = '';
    sections.forEach(sec => {
      let items = dateData[sec.cat] || [];
      if (activeFilter !== 'all') {
        items = items.filter(i => i.category === activeFilter);
      }
      if (items.length > 0) {
        html += renderSectionHeader(sec.num, sec.title, sec.sub);
        html += '<div class="card-grid">';
        html += items.map((item, i) => renderCard(item, i, true)).join('');
        html += '</div>';
      }
    });

    if (!html) {
      // Check if there's content but filtered out
      const totalItems = (dateData.gameUI?.length || 0) + (dateData.screenshots?.length || 0) + (dateData.reflections?.length || 0);
      if (totalItems > 0) {
        html = `<div class="empty-state fade-in"><div class="empty-icon">🔍</div><p>该分类下没有内容</p></div>`;
      } else {
        html = renderEmpty();
      }
    }

    return html;
  }

  function renderAllContent(items, activeFilter) {
    if (!items.length) return renderEmpty();

    let filtered = items;
    if (activeFilter !== 'all') {
      filtered = items.filter(i => i.category === activeFilter);
    }
    if (!filtered.length) {
      return `<div class="empty-state fade-in"><div class="empty-icon">🔍</div><p>该分类下没有内容</p></div>`;
    }

    return '<div class="card-grid">' + filtered.map((item, i) => renderCard(item, i, true)).join('') + '</div>';
  }

  function renderEmpty() {
    return `
      <div class="empty-state fade-in">
        <div class="empty-icon">—</div>
        <p>还没有内容</p>
        <p style="font-size:13px;color:var(--text-muted);margin-top:4px">点击导航栏选择分类后，点击「+ 发布新内容」开始分享</p>
      </div>
    `;
  }

  // ========== Calendar Panel ==========

  function renderCalendar(dates, currentDate) {
    const now = new Date();
    const [cy, cm] = currentDate ? currentDate.split('-').map(Number) : [now.getFullYear(), now.getMonth() + 1];
    const year = cy || now.getFullYear();
    const month = cm || now.getMonth() + 1;
    const today = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;

    const firstDay = new Date(year, month - 1, 1).getDay();
    const daysInMonth = new Date(year, month, 0).getDate();
    const dateSet = new Set(dates);

    const monthNames = ['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'];

    let daysHtml = '';
    for (let i = 0; i < firstDay; i++) daysHtml += '<div></div>';
    for (let d = 1; d <= daysInMonth; d++) {
      const ds = `${year}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const has = dateSet.has(ds);
      const isToday = ds === today;
      const isCurrent = ds === currentDate;
      daysHtml += `<button class="cal-day${has?' has-content':''}${isToday?' today':''}"
        onclick="App.selectDate('${ds}')"
        style="${isCurrent?'outline:2px solid var(--accent-gold);outline-offset:-2px':''}">${d}</button>`;
    }

    return `
      <div class="calendar-overlay" id="calendar-overlay" onclick="if(event.target===this)App.closeCalendar()">
        <div class="calendar-panel">
          <div class="cal-header">
            <h3>${year}年 ${monthNames[month-1]}</h3>
            <div class="cal-month-nav">
              <button onclick="App.calPrevMonth()">←</button>
              <button onclick="App.calNextMonth()">→</button>
            </div>
          </div>
          <div class="cal-weekdays">
            ${['日','一','二','三','四','五','六'].map(d=>`<span>${d}</span>`).join('')}
          </div>
          <div class="cal-days">${daysHtml}</div>
          <button class="cal-close" onclick="App.closeCalendar()">关闭</button>
        </div>
      </div>
    `;
  }

  // ========== Bookmarks Panel ==========

  function renderBookmarksPanel(bookmarks) {
    if (!bookmarks.length) {
      return `
        <div class="bookmarks-overlay" id="bookmarks-overlay" onclick="if(event.target===this)App.closeBookmarks()">
          <div class="bookmarks-panel">
            <h3>📌 我的收藏</h3>
            <div class="empty-state" style="padding:30px 0">
              <div class="empty-icon">☆</div><p>还没有收藏内容</p>
              <p style="font-size:13px;color:var(--text-muted);margin-top:4px">点击卡片上的 ☆ 收藏按钮</p>
            </div>
            <button class="cal-close" onclick="App.closeBookmarks()">关闭</button>
          </div>
        </div>
      `;
    }
    return `
      <div class="bookmarks-overlay" id="bookmarks-overlay" onclick="if(event.target===this)App.closeBookmarks()">
        <div class="bookmarks-panel">
          <h3>📌 我的收藏 (${bookmarks.length})</h3>
          <div class="bookmarks-list">
            ${bookmarks.map(b => {
              const meta = CAT_META[b.category] || {};
              return `
                <div class="bookmark-item">
                  <span class="bm-title" onclick="App.openDetail('${b.category}','${b.id}');App.closeBookmarks()">
                    ${meta.icon} ${escapeHtml(b.title)}
                  </span>
                  <span class="bm-cat">${meta.label}</span>
                  <button class="bm-remove" onclick="App.removeBookmark('${b.category}','${b.id}')">✕</button>
                </div>
              `;
            }).join('')}
          </div>
          <button class="cal-close" onclick="App.closeBookmarks()">关闭</button>
        </div>
      </div>
    `;
  }

  // ========== Detail Modal ==========

  function renderDetail(item) {
    const meta = CAT_META[item.category] || {};
    const tagHtml = item.tags?.map(t => `<span class="card-tag">${escapeHtml(t)}</span>`).join('') || '';

    return `
      <div class="modal-overlay" id="detail-modal">
        <div class="modal detail-modal">
          <button class="modal-close" onclick="App.closeModal('detail-modal')">✕</button>
          ${item.image ? `
            <div class="detail-image"><img src="${item.image}" alt="${escapeHtml(item.title)}"></div>
          ` : ''}
          <div class="detail-body">
            <div class="detail-meta">
              <span>${meta.icon} ${meta.label}</span>
              <span>·</span>
              <span>${item.date}</span>
            </div>
            <h2 class="detail-title">${escapeHtml(item.title)}</h2>
            ${item.game ? `<span style="color:var(--text-muted);font-size:14px">🎯 ${escapeHtml(item.game)}</span>` : ''}
            <div class="detail-content">${(item.content || item.desc || '').replace(/\n/g, '<br>')}</div>
            ${tagHtml ? `<div class="detail-tags">${tagHtml}</div>` : ''}
          </div>
          <div class="detail-footer">
            <span style="color:var(--text-muted);font-size:13px">${item.date}</span>
            <button class="btn-like" onclick="Storage.toggleLike('${item.category}','${item.id}');App.refresh();App.closeModal('detail-modal')">
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
              <div class="form-group"><label>游戏名称</label>
                <input type="text" name="game" placeholder="如：原神、崩坏：星穹铁道..." maxlength="50"></div>
            ` : ''}
            <div class="form-group">
              <label>${isReflection ? '正文' : '描述'}</label>
              ${isReflection ? `<textarea name="content" required placeholder="写下你的感悟..." rows="8" maxlength="5000"></textarea>`
              : `<textarea name="desc" required placeholder="描述一下..." rows="4" maxlength="500"></textarea>`}
            </div>
            <div class="form-group">
              <label>标签（逗号分隔）</label>
              <input type="text" name="tags" placeholder="如：RPG, 界面设计, 心得" maxlength="200">
            </div>
            ${!isReflection ? `
              <div class="form-group"><label>上传图片</label>
                <div class="upload-area" id="upload-area">
                  <input type="file" name="image" accept="image/png,image/jpeg,image/webp,image/gif"
                    onchange="App.handleImagePreview(this)" style="display:none" id="image-input">
                  <div class="upload-placeholder" onclick="document.getElementById('image-input').click()">
                    <span class="upload-icon">📁</span><p>点击选择图片</p>
                    <small>支持 JPG / PNG / WebP / GIF，最大 10MB</small></div>
                  <div class="upload-preview" id="image-preview" style="display:none">
                    <img src="" alt="预览">
                    <button type="button" class="btn-remove-img" onclick="App.clearImagePreview()">✕</button></div>
                </div>
                <div class="upload-status" id="upload-status"></div></div>
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

  // ========== Search Bar ==========

  function renderSearchBar() {
    return `
      <div class="search-bar" style="margin-bottom:16px">
        <input type="text" id="search-input" placeholder="搜索标题、标签、游戏名称..."
          oninput="App.handleSearch(this.value)"
          style="width:100%;padding:10px 16px;border:1px solid var(--border);border-radius:var(--radius-md);
          font-size:var(--font-body);font-family:inherit;outline:none;
          transition:all var(--transition);background:var(--card-bg)">
      </div>
    `;
  }

  // ========== Archive View ==========

  function renderArchive(dates, currentDate) {
    if (!dates.length) return renderEmpty();
    const dateSet = new Set(dates);
    return `
      <div class="day-title fade-in" style="margin-bottom:20px">📅 归档</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        ${dates.map(d => {
          const isCurrent = d === currentDate;
          const parts = d.split('-');
          const label = `${parseInt(parts[1])}月${parseInt(parts[2])}日`;
          return `<button class="filter-pill ${isCurrent ? 'active' : ''}"
            onclick="App.selectDate('${d}');App.navigate('home')"
            style="font-size:var(--font-sm);padding:8px 14px">📄 ${label}</button>`;
        }).join('')}
      </div>
    `;
  }

  // ========== Home Hero ==========

  function renderHomeHero() {
    return `
      <div class="day-title fade-in" style="margin-bottom:24px">
        Prieste<span style="color:var(--accent-gold)">Gaming</span>Space
        <span class="day-date" style="margin-left:12px">游戏与生活的交集</span>
      </div>
    `;
  }

  // ========== Toast ==========

  function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} fade-in`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 2500);
  }

  // ========== Confirm ==========

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
      overlay.querySelector('#confirm-yes').onclick = () => { resolve(true); overlay.remove(); };
      overlay.querySelector('#confirm-no').onclick = () => { resolve(false); overlay.remove(); };
      overlay.onclick = (e) => { if (e.target === overlay) { resolve(false); overlay.remove(); } };
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

  function formatDateDisplay(dateStr) {
    if (!dateStr || dateStr === '—') return '';
    const parts = dateStr.split('-');
    return `${parts[0]}年${parseInt(parts[1])}月${parseInt(parts[2])}日`;
  }

  // ========== Password Gate ==========

  function renderPasswordGate() {
    return `
      <div class="modal-overlay" id="password-gate" style="align-items:center;background:var(--bg);backdrop-filter:none" onclick="if(event.target===this)App.closePasswordGate()">
        <div class="modal" style="max-width:380px;padding:32px;text-align:center;position:relative">
          <button class="modal-close" onclick="App.closePasswordGate()" style="position:absolute;top:12px;right:12px">✕</button>
          <div style="font-size:48px;margin-bottom:12px">🌿</div>
          <h3 style="font-size:20px;font-weight:700;margin-bottom:6px">生活与自然</h3>
          <p style="color:var(--text-muted);font-size:14px;margin-bottom:20px">此内容已加密，请输入密码查看</p>
          <form onsubmit="App.verifyPassword(event)" style="display:flex;flex-direction:column;gap:12px">
            <input type="password" id="pwd-input" placeholder="输入密码" required
              style="width:100%;padding:12px 16px;border:1px solid var(--border);border-radius:var(--radius-sm);
              font-size:16px;text-align:center;outline:none;font-family:inherit;letter-spacing:4px"
              autofocus>
            <p id="pwd-error" style="color:var(--danger);font-size:13px;display:none">密码错误，请重试</p>
            <button type="submit" class="btn-submit" style="width:100%">解锁 🔓</button>
          </form>
        </div>
      </div>
    `;
  }

  // ========== Public API ==========
  return {
    CAT_META, NAV_TABS, FILTER_PILLS,
    renderStatsBar, renderNavTabs, renderSubBar, renderDayTitle,
    renderSectionHeader, renderCard, renderContentByDate, renderAllContent,
    renderCalendar, renderBookmarksPanel, renderDetail, renderCreateModal,
    renderSearchBar, renderArchive, renderHomeHero, renderEmpty, renderPasswordGate,
    showToast, showConfirm, escapeHtml, truncate, formatDateDisplay
  };
})();
