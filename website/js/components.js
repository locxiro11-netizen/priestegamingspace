/**
 * PriesteGamingSpace v3 — UI Components
 * Daily Forge style: stats bar, nav tabs, date selector, calendar, sign-in, bookmarks
 */
const Components = (() => {

  const CAT_META = {
    home:        { label: '全部',       icon: '', key: 'home' },
    news:        { label: '游戏资讯',   icon: '📰', key: 'news' },
    gameUI:      { label: '游戏UI分享', icon: '🎮', key: 'gameUI' },
    screenshots: { label: '游戏截图',   icon: '📸', key: 'screenshots' },
    reflections: { label: '工作感悟',   icon: '📝', key: 'reflections' },
    life:        { label: '生活与自然', icon: '🌿', key: 'life' }
  };

  const NAV_TABS = [
    { id: 'home',        label: '精选栏目' },
    { id: 'news',        label: '📰 游戏资讯' },
    { id: 'gameUI',      label: '游戏UI' },
    { id: 'screenshots', label: '游戏截图' },
    { id: 'reflections', label: '工作感悟' },
    { id: 'life',        label: '🌿 生活与自然' },
    { id: 'archive',     label: '归档' }
  ];

  const FILTER_PILLS = [
    { id: 'all',         label: '全部' },
    { id: 'news',        label: '游戏资讯' },
    { id: 'gameUI',      label: '游戏UI' },
    { id: 'screenshots', label: '游戏截图' },
    { id: 'reflections', label: '工作感悟' },
    { id: 'life',        label: '生活与自然' }
  ];

  // ========== Stats Bar ==========

  function renderStatsBar(stats, totalDays) {
    const items = [
      { num: stats.news, label: '游戏资讯', icon: '📰' },
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

  /** 资讯按媒体分的子页签。sources 形如 [{key,label,count}] */
  function renderSourceTabs(sources, active) {
    const total = sources.reduce((s, x) => s + x.count, 0);
    const items = [{ key: 'all', label: '全部', count: total }, ...sources];
    return `
      <div class="source-tabs">
        ${items.map(s => `
          <button class="source-tab${active === s.key ? ' active' : ''}"
            data-src="${escapeHtml(s.key)}"
            onclick="App.setNewsSource(this.dataset.src)">
            ${escapeHtml(s.label)}<span class="src-count">${s.count}</span>
          </button>`).join('')}
      </div>
    `;
  }

  /**
   * 资讯按内容类型分的子页签：全部 / 3A游戏 / 独立游戏。
   * counts 形如 { all: 80, '3a': 45, indie: 20, other: 15 }。
   * 「综合」不单独出页签——它装的是行业动态、平台政策这类不好归类的，
   * 数量再多也只是兜底，占一个位置反而让三个页签都变得没重点。
   */
  function renderGenreTabs(counts, active) {
    const items = [
      { key: 'all', label: '全部', icon: '📰', count: counts.all || 0 },
      { key: '3a', label: '3A游戏', icon: '🎮', count: counts['3a'] || 0 },
      { key: 'indie', label: '独立游戏', icon: '🕹️', count: counts.indie || 0 },
    ];
    return `
      <div class="genre-tabs">
        ${items.map(t => `
          <button class="genre-tab${active === t.key ? ' active' : ''}"
            data-genre="${t.key}"
            onclick="App.setNewsGenre(this.dataset.genre)">
            <span class="genre-ico">${t.icon}</span>${escapeHtml(t.label)}<span class="src-count">${t.count}</span>
          </button>`).join('')}
      </div>
    `;
  }

  function renderSubBar(currentTab, currentDateIndex, totalDates, dates, activeFilter, lifeUnlocked, canPublish) {
    const currentDate = dates[currentDateIndex] || '—';
    const dateDisplay = formatDateDisplay(currentDate);
    const canPrev = currentDateIndex < totalDates - 1;
    const canNext = currentDateIndex > 0;
    // 资讯页签展示全部历史（按时间倒序），日期翻页对它没意义，换成总量提示
    const showDateNav = currentTab !== 'news';

    return `
      <div class="date-selector">
        ${showDateNav ? `
          <button class="date-arrow" onclick="App.prevDate()" ${canPrev ? '' : 'disabled'}>←</button>
          <span class="date-text">
            <span class="day-num">Day ${String(totalDates - currentDateIndex).padStart(3,'0')}</span>
            / ${totalDates}
          </span>
          <button class="date-arrow" onclick="App.nextDate()" ${canNext ? '' : 'disabled'}>→</button>
          <button class="cal-btn" onclick="App.openCalendar()">📅</button>
        ` : `
          <span class="date-text"><span class="day-num">全部资讯</span></span>
        `}
      </div>

      <div class="filter-pills">
        <button class="filter-pill" onclick="App.openBookmarks()">📌 收藏</button>
        ${canPublish ? '<button class="filter-pill" onclick="App.openCreateModal()" style="background:var(--accent);color:#FFF;border-color:var(--accent)">📝 发布</button>' : ''}
      </div>
    `;
  }

  // ========== Cover Image ==========

  // 卡片封面区最宽 1036 CSS px。原图不到这个宽度的 1/1.5 就别硬撑满，
  // 否则浏览器插值放大出来就是一团糊——交给 fitCover() 降级处理。
  const COVER_MAX_UPSCALE = 1.25;

  function coverAttrs(item, extraClass) {
    // 已知尺寸就写上 width/height，浏览器能提前按原比例占好位，
    // 图片加载完不会把下面的文字顶下去
    const w = Number(item.image_w) || 0;
    const h = Number(item.image_h) || 0;
    const dim = (w && h) ? ` width="${w}" height="${h}"` : '';
    return `${dim} loading="lazy" decoding="async" referrerpolicy="no-referrer"`;
  }

  /**
   * 图片加载/失败后的兜底：
   *  - 源站只给得到小图 → 加 is-lowres，改成「模糊底 + 原尺寸居中」，不拉伸
   *  - 图挂了（防盗链、证书不匹配、404）→ 整块藏掉，别留个破图图标
   */
  function fitCover(img) {
    if (!img || img.dataset.fitted) return;
    img.dataset.fitted = '1';
    const box = img.parentElement;
    if (!box) return;
    const nat = img.naturalWidth;
    if (!nat) return;                       // 加载失败，交给 onerror
    const disp = img.clientWidth || box.clientWidth;
    if (disp && nat * COVER_MAX_UPSCALE < disp) {
      box.style.setProperty('--cover-src', `url("${img.currentSrc || img.src}")`);
      box.style.setProperty('--cover-maxw',
        Math.round(Math.min(disp, nat * COVER_MAX_UPSCALE)) + 'px');
      box.classList.add('is-lowres');
    }
  }

  function coverFailed(img) {
    const box = img && img.parentElement;
    if (!box) return;
    // 直接把整块收掉，卡片退化成纯文字卡片，比留一个破图图标干净
    box.style.display = 'none';
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
        <span class="sec-line"></span>
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
            <img src="${item.image}" alt="${escapeHtml(item.title)}"${coverAttrs(item)}
              onload="Components.fitCover(this)" onerror="Components.coverFailed(this)"
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
      { cat: 'news', num: 1, title: '游戏资讯', sub: 'Gaming News' },
      { cat: 'gameUI', num: 2, title: '游戏UI分享', sub: 'Game UI Sharing' },
      { cat: 'screenshots', num: 3, title: '游戏截图', sub: 'Game Screenshots' },
      { cat: 'reflections', num: 4, title: '工作感悟', sub: 'Work Reflections' },
      { cat: 'life', num: 5, title: '生活与自然', sub: 'Life & Nature' }
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
      const totalItems = (dateData.news?.length || 0) + (dateData.gameUI?.length || 0) + (dateData.screenshots?.length || 0) + (dateData.reflections?.length || 0);
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

  /** 取链接的域名，用于「阅读原文」处显示出处。 */
  function originHost(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch (e) {
      return (url || '').replace(/^https?:\/\//, '').split('/')[0];
    }
  }

  // 视频 URL 处理：去掉 autoplay（骚扰且耗流量）；YouTube 生成可点击的观看链接
  function sanitizeVideoUrl(url) {
    if (!url) return url;
    return url.replace(/([?&])autoplay=1&?/, '$1').replace(/[?&]$/, '');
  }

  function videoWatchUrl(url) {
    if (!url) return '';
    const m = url.match(/youtube(?:-nocookie)?\.com\/embed\/([\w-]+)/);
    if (m) return 'https://www.youtube.com/watch?v=' + m[1];
    return url;
  }

  function isYoutube(url) {
    return /youtube(?:-nocookie)?\.com/.test(url || '');
  }

  // content_html 里的内嵌 iframe 同样去掉 autoplay
  function sanitizeContentHtml(html) {
    if (!html) return html;
    return html.replace(/(<iframe[^>]*src="[^"]*?)autoplay=1&?/g, '$1');
  }

  function renderDetail(item) {
    const meta = CAT_META[item.category] || {};
    const tagHtml = item.tags?.map(t => `<span class="card-tag">${escapeHtml(t)}</span>`).join('') || '';

    return `
      <div class="modal-overlay" id="detail-modal">
        <div class="modal detail-modal">
          <button class="modal-close" onclick="App.closeModal('detail-modal')">✕</button>
          ${item.video ? `
            <div class="detail-video">
              <iframe src="${sanitizeVideoUrl(item.video)}" frameborder="0"
                allow="autoplay; encrypted-media; picture-in-picture"
                referrerpolicy="strict-origin-when-cross-origin"
                allowfullscreen loading="lazy" title="${escapeHtml(item.title)}"></iframe>
            </div>
            ${isYoutube(item.video) ? `
              <div class="video-fallback">
                📺 视频托管在 YouTube，若无法加载可
                <a href="${videoWatchUrl(item.video)}" target="_blank" rel="noopener">点击前往观看 →</a>
              </div>
            ` : ''}
          ` : (item.image ? `
            <div class="detail-image">
              <img src="${item.image}" alt="${escapeHtml(item.title)}"${coverAttrs(item)}
                onload="Components.fitCover(this)" onerror="Components.coverFailed(this)">
            </div>
          ` : '')}
          <div class="detail-body">
            <div class="detail-meta">
              <span>${meta.icon} ${meta.label}</span>
              <span>·</span>
              <span>${item.date}</span>
            </div>
            <h2 class="detail-title">${escapeHtml(item.title)}</h2>
            ${item.game ? `<span style="color:var(--text-muted);font-size:14px">🎯 ${escapeHtml(item.game)}</span>` : ''}
            ${item.content_html ? `
              ${item.video && item.image ? `
                <div class="detail-image">
                  <img src="${item.image}" alt=""${coverAttrs(item)}
                    onload="Components.fitCover(this)" onerror="Components.coverFailed(this)">
                </div>` : ''}
              <div class="detail-content article-body">${sanitizeContentHtml(item.content_html)}</div>
            ` : `
              <div class="detail-content">${(item.content || item.desc || '').replace(/\n/g, '<br>')}</div>
            `}
            ${item.source_url ? `
              <a class="detail-origin" href="${escapeHtml(item.source_url)}"
                 target="_blank" rel="noopener">
                <span class="origin-icon">🔗</span>
                <span class="origin-text">
                  <span class="origin-label">阅读原文</span>
                  <span class="origin-host">${escapeHtml(originHost(item.source_url))}${item.source ? ' · ' + escapeHtml(item.source) : ''}</span>
                </span>
                <span class="origin-arrow">→</span>
              </a>
            ` : ''}
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
    renderSearchBar, renderSourceTabs, renderGenreTabs, renderArchive, renderHomeHero, renderEmpty,
    renderPasswordGate, showToast, showConfirm, escapeHtml, truncate, formatDateDisplay,
    fitCover, coverFailed
  };
})();
