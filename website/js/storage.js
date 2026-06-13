/**
 * PriesteGamingSpace - Storage Layer
 * localStorage CRUD for game UI, screenshots, and reflections
 */
const Storage = (() => {
  const KEYS = {
    gameUI: 'pgs_game_ui',
    screenshots: 'pgs_screenshots',
    reflections: 'pgs_reflections'
  };

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

  function getRecent(limit = 3) {
    const all = [
      ...getAll('gameUI').map(i => ({ ...i, category: 'gameUI' })),
      ...getAll('screenshots').map(i => ({ ...i, category: 'screenshots' })),
      ...getAll('reflections').map(i => ({ ...i, category: 'reflections' }))
    ];
    return all.sort((a, b) => b.date.localeCompare(a.date)).slice(0, limit);
  }

  function getStats() {
    return {
      gameUI: getAll('gameUI').length,
      screenshots: getAll('screenshots').length,
      reflections: getAll('reflections').length
    };
  }

  function exportAll() {
    return {
      gameUI: getAll('gameUI'),
      screenshots: getAll('screenshots'),
      reflections: getAll('reflections'),
      exportedAt: _now()
    };
  }

  function importAll(data) {
    if (!data || typeof data !== 'object') return false;
    if (Array.isArray(data.gameUI)) _write(KEYS.gameUI, data.gameUI);
    if (Array.isArray(data.screenshots)) _write(KEYS.screenshots, data.screenshots);
    if (Array.isArray(data.reflections)) _write(KEYS.reflections, data.reflections);
    return true;
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
    importAll
  };
})();
