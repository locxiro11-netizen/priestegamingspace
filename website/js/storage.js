/**
 * PriesteGamingSpace - Storage Layer
 * localStorage CRUD for game UI, screenshots, and reflections
 */
const Storage = (() => {
  const KEYS = {
    gameUI: 'pgs_game_ui',
    screenshots: 'pgs_screenshots',
    reflections: 'pgs_reflections',
    life: 'pgs_life',
    signin: 'pgs_signin',
    bookmarks: 'pgs_bookmarks'
  };

  let _sharedLoaded = false;

  // ========== Helpers ==========

  function _read(key) {
    try {
      return JSON.parse(localStorage.getItem(key)) || [];
    } catch {
      return [];
    }
  }

  function _write(key, data) {
    try {
      localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
      if (e.name === 'QuotaExceededError') {
        alert('存储空间不足！请删除一些旧内容后重试。');
      } else {
        throw e;
      }
    }
  }

  function _uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function _now() {
    return new Date().toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit'
    });
  }

  // ========== Image Compression ==========

  function compressImage(file, maxWidth = 1200, quality = 0.7) {
    return new Promise((resolve, reject) => {
      if (!file.type.match(/image\/(png|jpeg|webp|gif)/)) {
        reject(new Error('不支持的图片格式，请使用 PNG / JPG / WebP / GIF'));
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        reject(new Error('图片不能超过 10MB'));
        return;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement('canvas');
          let { width, height } = img;
          if (width > maxWidth) {
            height = Math.round(height * maxWidth / width);
            width = maxWidth;
          }
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, width, height);
          const base64 = canvas.toDataURL('image/jpeg', quality);
          resolve({ base64, width, height });
        };
        img.onerror = () => reject(new Error('图片加载失败'));
        img.src = e.target.result;
      };
      reader.onerror = () => reject(new Error('文件读取失败'));
      reader.readAsDataURL(file);
    });
  }

  // ========== Generic CRUD ==========

  function getAll(category) {
    return _read(KEYS[category]);
  }

  function getById(category, id) {
    const items = _read(KEYS[category]);
    return items.find(item => item.id === id) || null;
  }

  function create(category, data) {
    const items = _read(KEYS[category]);
    const item = { id: _uid(), date: _now(), likes: 0, ...data };
    items.unshift(item);
    _write(KEYS[category], items);
    return item;
  }

  function update(category, id, updates) {
    const items = _read(KEYS[category]);
    const idx = items.findIndex(item => item.id === id);
    if (idx === -1) return null;
    items[idx] = { ...items[idx], ...updates };
    _write(KEYS[category], items);
    return items[idx];
  }

  function remove(category, id) {
    const items = _read(KEYS[category]);
    const idx = items.findIndex(item => item.id === id);
    if (idx === -1) return false;
    items.splice(idx, 1);
    _write(KEYS[category], items);
    return true;
  }

  function toggleLike(category, id) {
    const items = _read(KEYS[category]);
    const item = items.find(item => item.id === id);
    if (item) {
      item.likes = (item.likes || 0) + 1;
      _write(KEYS[category], items);
      return item.likes;
    }
    return 0;
  }

  function search(category, query) {
    if (!query) return getAll(category);
    const q = query.toLowerCase();
    return _read(KEYS[category]).filter(item =>
      (item.title && item.title.toLowerCase().includes(q)) ||
      (item.desc && item.desc.toLowerCase().includes(q)) ||
      (item.content && item.content.toLowerCase().includes(q)) ||
      (item.tags && item.tags.some(t => t.toLowerCase().includes(q))) ||
      (item.game && item.game.toLowerCase().includes(q))
    );
  }

  const ALL_CATS = ['gameUI','screenshots','reflections','life'];

  function getRecent(limit = 3) {
    const all = [];
    ALL_CATS.forEach(cat => {
      getAll(cat).forEach(item => all.push({ ...item, category: cat }));
    });
    return all.sort((a, b) => b.date.localeCompare(a.date)).slice(0, limit);
  }

  function getStats() {
    return {
      gameUI: getAll('gameUI').length,
      screenshots: getAll('screenshots').length,
      reflections: getAll('reflections').length,
      life: getAll('life').length
    };
  }

  function exportAll() {
    return {
      gameUI: getAll('gameUI'),
      screenshots: getAll('screenshots'),
      reflections: getAll('reflections'),
      life: getAll('life'),
      exportedAt: _now()
    };
  }

  function importAll(data) {
    if (!data || typeof data !== 'object') return false;
    if (Array.isArray(data.gameUI)) _write(KEYS.gameUI, data.gameUI);
    if (Array.isArray(data.screenshots)) _write(KEYS.screenshots, data.screenshots);
    if (Array.isArray(data.reflections)) _write(KEYS.reflections, data.reflections);
    if (Array.isArray(data.life)) _write(KEYS.life, data.life);
    return true;
  }

  // ========== Shared Content (JSON file) ==========

  function loadSharedContent() {
    if (_sharedLoaded) return Promise.resolve();
    return fetch('data/content.json')
      .then(r => r.json())
      .then(shared => {
        ['gameUI','screenshots','reflections','life'].forEach(cat => {
          const local = _read(KEYS[cat]);
          const sharedItems = Array.isArray(shared[cat]) ? shared[cat] : [];
          const localIds = new Set(local.map(i => i.id));
          const merged = [...local];
          sharedItems.forEach(si => {
            if (!localIds.has(si.id)) merged.push(si);
          });
          _write(KEYS[cat], merged);
        });
        _sharedLoaded = true;
      })
      .catch(() => {}); // fallback: local only
  }

  function getSharedData() {
    return {
      gameUI: _read(KEYS.gameUI),
      screenshots: _read(KEYS.screenshots),
      reflections: _read(KEYS.reflections),
      life: _read(KEYS.life)
    };
  }

  // ========== Sign-in ==========

  function _dateKey(date) {
    const d = date || new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  function _todayKey() { return _dateKey(new Date()); }

  function checkIn() {
    const data = getSignInData();
    const today = _todayKey();
    if (data.lastDate === today) return data; // already checked in

    const yesterday = _dateKey(new Date(Date.now() - 86400000));
    if (data.lastDate === yesterday) {
      data.streak += 1;
    } else {
      data.streak = 1;
    }
    data.lastDate = today;
    data.totalDays = (data.totalDays || 0) + 1;
    _write(KEYS.signin, [data]);
    return data;
  }

  function getSignInData() {
    return _read(KEYS.signin)[0] || { lastDate: null, streak: 0, totalDays: 0 };
  }

  // ========== Calendar / Date ==========

  function getDatesWithContent() {
    const dateSet = new Set();
    ALL_CATS.forEach(cat => {
      getAll(cat).forEach(item => {
        // Extract date part from "2026/06/15 14:30" format
        const m = item.date.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
        if (m) dateSet.add(`${m[1]}-${String(parseInt(m[2])).padStart(2,'0')}-${String(parseInt(m[3])).padStart(2,'0')}`);
      });
    });
    return [...dateSet].sort().reverse();
  }

  function getContentByDate(dateStr) {
    const result = { gameUI: [], screenshots: [], reflections: [], life: [] };
    ALL_CATS.forEach(cat => {
      getAll(cat).forEach(item => {
        const m = item.date.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
        if (m) {
          const d = `${m[1]}-${String(parseInt(m[2])).padStart(2,'0')}-${String(parseInt(m[3])).padStart(2,'0')}`;
          if (d === dateStr) {
            result[cat].push({ ...item, category: cat });
          }
        }
      });
    });
    return result;
  }

  function getAllContentSorted() {
    const all = [];
    ALL_CATS.forEach(cat => {
      getAll(cat).forEach(item => all.push({ ...item, category: cat }));
    });
    return all.sort((a, b) => b.date.localeCompare(a.date));
  }

  function getTotalDays() {
    return getDatesWithContent().length;
  }

  // ========== Bookmarks ==========

  function toggleBookmark(cat, id) {
    const bookmarks = _read(KEYS.bookmarks);
    const existing = bookmarks.findIndex(b => b.id === id);
    if (existing >= 0) {
      bookmarks.splice(existing, 1);
      _write(KEYS.bookmarks, bookmarks);
      return false;
    }
    bookmarks.push({ cat, id, addedAt: _now() });
    _write(KEYS.bookmarks, bookmarks);
    return true;
  }

  function getBookmarks() {
    const bookmarks = _read(KEYS.bookmarks);
    return bookmarks.map(b => {
      const item = getById(b.cat, b.id);
      return item ? { ...item, category: b.cat, bookmarkAddedAt: b.addedAt } : null;
    }).filter(Boolean);
  }

  function isBookmarked(id) {
    return _read(KEYS.bookmarks).some(b => b.id === id);
  }

  // ========== Public API ==========
  return {
    KEYS,
    compressImage,
    getAll,
    getById,
    create,
    update,
    remove,
    toggleLike,
    search,
    getRecent,
    getStats,
    exportAll,
    importAll,
    checkIn,
    getSignInData,
    getDatesWithContent,
    getContentByDate,
    getAllContentSorted,
    getTotalDays,
    toggleBookmark,
    getBookmarks,
    isBookmarked,
    loadSharedContent,
    getSharedData
  };
})();
