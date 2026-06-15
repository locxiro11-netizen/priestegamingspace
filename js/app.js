/**
 * PriesteGamingSpace v3 — Application Core
 * Daily Forge style: sign-in, calendar, date selector, bookmarks
 */
const App = (() => {
  let _currentTab = 'home';
  let _currentDateIndex = 0;
  let _activeFilter = 'all';
  let _searchQuery = '';
  let _dates = [];
  let _calendarYear, _calendarMonth;
  let _lifeUnlocked = false;

  // ========== Init ==========

  function init() {
    Storage.loadSharedContent().then(() => {
      _dates = Storage.getDatesWithContent();
      const now = new Date();
      _calendarYear = now.getFullYear();
      _calendarMonth = now.getMonth() + 1;
      autoCheckIn();
      bindEvents();
      render();
    });
  }

  function autoCheckIn() {
    const data = Storage.checkIn();
    updateSignInBtn(data);
  }

  function bindEvents() {
    document.querySelector('#stats-bar').addEventListener('click', (e) => {});
    // Nav tabs
    document.querySelector('#nav-tabs').addEventListener('click', (e) => {
      const tab = e.target.closest('.nav-tab');
      if (tab) navigate(tab.dataset.tab);
    });
    // Card actions (like, bookmark, delete)
    document.querySelector('#content').addEventListener('click', (e) => {
      const likeBtn = e.target.closest('[data-action="like"]');
      const bmBtn = e.target.closest('[data-action="bookmark"]');
      const delBtn = e.target.closest('[data-action="delete"]');
      if (likeBtn) {
        e.stopPropagation();
        Storage.toggleLike(likeBtn.dataset.cat, likeBtn.dataset.id);
        refresh();
      }
      if (bmBtn) {
        e.stopPropagation();
        const added = Storage.toggleBookmark(bmBtn.dataset.cat, bmBtn.dataset.id);
        Components.showToast(added ? '已收藏 ★' : '已取消收藏');
        refresh();
      }
      if (delBtn) {
        e.stopPropagation();
        handleDelete(delBtn.dataset.cat, delBtn.dataset.id);
      }
    });
    // Sign-in
    document.querySelector('#signin-btn').addEventListener('click', () => {
      const data = Storage.checkIn();
      updateSignInBtn(data);
      Components.showToast(`签到成功！连续签到 ${data.streak} 天 🔥`);
    });
    // Search
    document.querySelector('#content').addEventListener('input', (e) => {
      if (e.target.id === 'search-input') handleSearch(e.target.value);
    });
    // Import
    document.querySelector('#import-file').addEventListener('change', handleImport);
  }

  function updateSignInBtn(data) {
    const btn = document.querySelector('#signin-btn');
    if (!btn) return;
    const today = new Date().toISOString().slice(0, 10);
    if (data.lastDate === today) {
      btn.className = 'header-signin checked';
      btn.innerHTML = `<span class="flame">🔥</span> 连续签到 <span class="streak">${data.streak}</span> 天`;
    } else {
      btn.className = 'header-signin';
      btn.innerHTML = `<span class="flame">🔥</span> 连续签到 <span class="streak">${data.streak}</span> 天`;
    }
  }

  // ========== Routing ==========

  function navigate(tab) {
    if (tab === 'life' && !_lifeUnlocked) {
      _currentTab = tab;
      showPasswordGate();
      return;
    }
    _currentTab = tab;
    _searchQuery = '';
    const si = document.querySelector('#search-input');
    if (si) si.value = '';
    render();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function refresh() {
    _dates = Storage.getDatesWithContent();
    render();
  }

  function setFilter(filter) {
    _activeFilter = filter;
    render();
  }

  function prevDate() {
    if (_currentDateIndex < _dates.length - 1) {
      _currentDateIndex++;
      refresh();
    }
  }

  function nextDate() {
    if (_currentDateIndex > 0) {
      _currentDateIndex--;
      refresh();
    }
  }

  function selectDate(dateStr) {
    const idx = _dates.indexOf(dateStr);
    if (idx >= 0) {
      _currentDateIndex = idx;
      closeCalendar();
      _currentTab = 'home';
      refresh();
    }
  }

  // ========== Calendar ==========

  function openCalendar() {
    closeCalendar();
    const cd = _dates[_currentDateIndex] || null;
    document.body.insertAdjacentHTML('beforeend', Components.renderCalendar(_dates, cd));
  }

  function closeCalendar() {
    const el = document.querySelector('#calendar-overlay');
    if (el) el.remove();
  }

  function calPrevMonth() {
    if (_calendarMonth === 1) { _calendarMonth = 12;
      _calendarYear--; } else _calendarMonth--;
    openCalendar();
  }

  function calNextMonth() {
    if (_calendarMonth === 12) { _calendarMonth = 1;
      _calendarYear++; } else _calendarMonth++;
    openCalendar();
  }

  // ========== Bookmarks ==========

  function openBookmarks() {
    closeBookmarks();
    const bms = Storage.getBookmarks();
    document.body.insertAdjacentHTML('beforeend', Components.renderBookmarksPanel(bms));
  }

  function closeBookmarks() {
    const el = document.querySelector('#bookmarks-overlay');
    if (el) el.remove();
  }

  function removeBookmark(cat, id) {
    Storage.toggleBookmark(cat, id);
    openBookmarks();
    refresh();
  }

  // ========== Render ==========

  function render() {
    const stats = Storage.getStats();
    let totalDays = Storage.getTotalDays();
    let dates = _dates;
    // Hide life data everywhere when locked
    if (!_lifeUnlocked) {
      stats.life = 0;
      // Filter dates that only have life content
      dates = dates.filter(d => {
        const dd = Storage.getContentByDate(d);
        return (dd.gameUI.length+dd.screenshots.length+dd.reflections.length) > 0;
      });
      totalDays = dates.length;
    }
    const currentDate = dates[_currentDateIndex] || null;

    // Set body class for background
    var curBg=localStorage.getItem('pgs_bg')||'none';
    document.body.className='bg-'+curBg;
    if(curBg==='upload'){
      var ud=localStorage.getItem('pgs_bg_upload');
      if(ud)document.body.style.backgroundImage='url('+ud+')';
    }else{document.body.style.backgroundImage='';}

    // Stats bar
    document.querySelector('#stats-bar').innerHTML = Components.renderStatsBar(stats, totalDays);

    // Nav tabs
    document.querySelector('#nav-tabs').innerHTML = Components.renderNavTabs(_currentTab);

    // Sub bar
    const hasDates = dates.length > 0;
    document.querySelector('#sub-bar').innerHTML = Components.renderSubBar(
      _currentTab, _currentDateIndex, dates.length, dates, _activeFilter, _lifeUnlocked
    );

    // Content
    const content = document.querySelector('#content');

    if (_currentTab === 'archive') {
      content.innerHTML = Components.renderArchive(dates, currentDate);
    } else if (_currentTab === 'home') {
      content.innerHTML = Components.renderHomeHero();
      if (currentDate) {
        content.innerHTML += Components.renderDayTitle(_currentDateIndex, dates.length, currentDate);
        const dateData = Storage.getContentByDate(currentDate);
        if (!_lifeUnlocked) delete dateData.life;
        content.innerHTML += Components.renderContentByDate(dateData, _activeFilter);
      } else {
        content.innerHTML += Components.renderEmpty();
      }
    } else if (_currentTab === 'life') {
      if (!_lifeUnlocked) { showPasswordGate(); return; }
      content.innerHTML = Components.renderSearchBar();
      if (currentDate) {
        const dateData = Storage.getContentByDate(currentDate);
        const items = dateData['life'] || [];
        content.innerHTML += `<div class="card-grid">${items.map((item,i) => Components.renderCard(item,i,true)).join('') || Components.renderEmpty()}</div>`;
      } else {
        content.innerHTML += Components.renderEmpty();
      }
    } else {
      // Category-specific view
      content.innerHTML = Components.renderSearchBar();
      if (currentDate) {
        const dateData = Storage.getContentByDate(currentDate);
        const items = dateData[_currentTab] || [];
        content.innerHTML += `<div class="card-grid">${items.map((item,i) => Components.renderCard(item,i,true)).join('') || Components.renderEmpty()}</div>`;
      } else {
        content.innerHTML += Components.renderEmpty();
      }
    }

    // Update sign-in
    updateSignInBtn(Storage.getSignInData());
    // Re-apply admin visibility (after innerHTML replaces DOM)
    if (typeof updateAdminUI === 'function') updateAdminUI();
  }

  // ========== Modal ==========

  function isAdmin() {
    if (sessionStorage.getItem('pgs_admin') === '1') return true;
    try {
      var d = JSON.parse(localStorage.getItem('pgs_admin'));
      if (d && d.exp > Date.now()) return true;
    } catch(e) {}
    return false;
  }

  function openCreateModal() {
    if (!isAdmin()) return;
    if (_currentTab === 'home' || _currentTab === 'archive') return;
    closeModal();
    document.body.insertAdjacentHTML('beforeend', Components.renderCreateModal(_currentTab));
    document.querySelector('#create-modal').addEventListener('click', (e) => {
      if (e.target.id === 'create-modal') closeModal();
    });
  }

  function openDetail(category, id) {
    const item = Storage.getById(category, id);
    if (!item) return;
    item.category = category;
    closeModal();
    document.body.insertAdjacentHTML('beforeend', Components.renderDetail(item));
    document.querySelector('#detail-modal').addEventListener('click', (e) => {
      if (e.target.id === 'detail-modal') closeModal();
    });
  }

  function closeModal(modalId) {
    const modals = modalId
      ? [document.querySelector(`#${modalId}`)]
      : document.querySelectorAll('.modal-overlay');
    modals.forEach(m => m?.remove());
  }

  // ========== CRUD ==========

  let _pendingImage = null;

  function handleImagePreview(input) {
    const file = input.files[0];
    const preview = document.querySelector('#image-preview');
    const placeholder = document.querySelector('.upload-placeholder');
    const status = document.querySelector('#upload-status');
    if (!file) return;
    status.textContent = '正在压缩图片...';
    status.className = 'upload-status loading';
    Storage.compressImage(file).then(result => {
      _pendingImage = result.base64;
      preview.querySelector('img').src = result.base64;
      preview.style.display = 'block';
      placeholder.style.display = 'none';
      status.textContent = `图片已就绪 (${Math.round(result.base64.length/1024)}KB)`;
      status.className = 'upload-status success';
    }).catch(err => {
      status.textContent = err.message;
      status.className = 'upload-status error';
      input.value = '';
    });
  }

  function clearImagePreview() {
    _pendingImage = null;
    const p = document.querySelector('#image-preview');
    const ph = document.querySelector('.upload-placeholder');
    const inp = document.querySelector('#image-input');
    const st = document.querySelector('#upload-status');
    if (p) p.style.display = 'none';
    if (ph) ph.style.display = 'flex';
    if (inp) inp.value = '';
    if (st) { st.textContent = '';
      st.className = 'upload-status'; }
  }

  function handleCreate(event, category) {
    event.preventDefault();
    const form = event.target;
    const submitBtn = form.querySelector('#submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = '发布中...';
    const formData = new FormData(form);
    const tags = formData.get('tags') ? formData.get('tags').split(/[,，]/).map(t => t.trim()).filter(Boolean) : [];
    const data = { title: formData.get('title').trim(), tags };
    if (category === 'reflections') data.content = formData.get('content').trim();
    else { data.desc = formData.get('desc')?.trim() || ''; if (_pendingImage) data.image = _pendingImage; }
    if (category === 'screenshots') data.game = formData.get('game')?.trim() || '';
    try {
      Storage.create(category, data);
      _pendingImage = null;
      closeModal();
      _dates = Storage.getDatesWithContent();
      _currentDateIndex = 0;
      refresh();
      Components.showToast('发布成功');
      // Trigger auto-sync
      syncToCloud();
    } catch (err) {
      Components.showToast('发布失败，请重试', 'error');
      submitBtn.disabled = false;
      submitBtn.textContent = '发布';
    }
  }

  async function handleDelete(category, id) {
    const confirmed = await Components.showConfirm('确定要删除这条内容吗？此操作不可恢复。');
    if (confirmed) {
      Storage.remove(category, id);
      _dates = Storage.getDatesWithContent();
      if (_currentDateIndex >= _dates.length) _currentDateIndex = Math.max(0, _dates.length - 1);
      refresh();
      Components.showToast('已删除');
      syncToCloud();
    }
  }

  function handleSearch(query) {
    _searchQuery = query;
    refresh();
  }

  // ========== Export / Import ==========

  function handleExport() {
    const data = Storage.exportAll();
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `PriesteGamingSpace_backup_${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    Components.showToast('导出成功');
  }

  function handleImport(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target.result);
        if (Storage.importAll(data)) {
          _dates = Storage.getDatesWithContent();
          Components.showToast('导入成功');
          refresh();
        } else Components.showToast('文件格式不正确', 'error');
      } catch { Components.showToast('文件解析失败', 'error'); }
    };
    reader.readAsText(file);
    event.target.value = '';
  }

  // ========== Password Gate ==========

  function showPasswordGate() {
    closePasswordGate();
    document.querySelector('#content').innerHTML = '';
    document.body.insertAdjacentHTML('beforeend', Components.renderPasswordGate());
    setTimeout(() => {
      const input = document.querySelector('#pwd-input');
      if (input) input.focus();
    }, 100);
  }

  function verifyPassword(event) {
    event.preventDefault();
    const input = document.querySelector('#pwd-input');
    const error = document.querySelector('#pwd-error');
    if (input.value === '22142214') {
      _lifeUnlocked = true;
      closePasswordGate();
      _currentTab = 'life';
      render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      Components.showToast('解锁成功 🌿');
    } else {
      if (error) error.style.display = 'block';
      input.value = '';
      input.focus();
    }
  }

  function closePasswordGate() {
    const el = document.querySelector('#password-gate');
    if (el) el.remove();
    if (!_lifeUnlocked) { _currentTab = 'home';
      render(); }
  }

  function unlockLife() {
    _lifeUnlocked = true;
    if (_currentTab === 'life') render();
  }

  // ========== Sync ==========

  function syncToCloud() {
    syncViaGitHub();
  }

  async function syncViaGitHub() {
    const token = localStorage.getItem('pgs_gh_token');
    if (!token) {
      // Try local server fallback
      try {
        const data = Storage.getSharedData();
        await fetch('http://localhost:9876/sync', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify(data)
        });
        Components.showToast('☁️ 已同步 (本地)');
      } catch(e) {}
      return;
    }
    try {
      const data = Storage.getSharedData();
      const content = btoa(unescape(encodeURIComponent(JSON.stringify(data, null, 2))));
      // Get current file SHA
      let sha = '';
      try {
        const r = await fetch('https://api.github.com/repos/locxiro11-netizen/priestegamingspace/contents/data/content.json', {
          headers: { 'Authorization': 'token '+token }
        });
        if (r.ok) { const j = await r.json(); sha = j.sha; }
      } catch(e) {}
      // Push update
      const body = { message: 'Auto-sync content', content: content, branch: 'main' };
      if (sha) body.sha = sha;
      const r = await fetch('https://api.github.com/repos/locxiro11-netizen/priestegamingspace/contents/data/content.json', {
        method: 'PUT',
        headers: { 'Authorization': 'token '+token, 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (r.ok) Components.showToast('☁️ 已同步到云端');
      else { const j = await r.json(); console.error('[Sync]', j.message); }
    } catch(e) {
      console.error('[Sync]', e);
      // Fallback to local server
      try {
        const data = Storage.getSharedData();
        await fetch('http://localhost:9876/sync', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify(data)
        });
      } catch(e2) {}
    }
  }

  function setGitHubToken(token) {
    localStorage.setItem('pgs_gh_token', token);
    Components.showToast('Token 已保存，同步就绪');
  }

  function getSyncData() {
    try {
      return JSON.parse(localStorage.getItem('pgs_sync_data') || 'null');
    } catch(e) { return null; }
  }

  function clearSyncFlag() {
    localStorage.removeItem('pgs_sync_pending');
  }

  // ========== Public API ==========
  return {
    init, navigate, refresh, setFilter,
    prevDate, nextDate, selectDate,
    openCalendar, closeCalendar, calPrevMonth, calNextMonth,
    openBookmarks, closeBookmarks, removeBookmark,
    openCreateModal, openDetail, closeModal,
    handleCreate, handleDelete, handleSearch,
    handleImagePreview, clearImagePreview,
    handleExport, handleImport,
    verifyPassword, showPasswordGate, closePasswordGate,
    unlockLife, syncToCloud, setGitHubToken
  };
})();

document.addEventListener('DOMContentLoaded', () => App.init());
