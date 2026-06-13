/**
 * PriesteGamingSpace — Application Core v2
 * Two-column layout · Sidebar routing · Daily Forge style
 */
const App = (() => {
  let _currentTab = 'home';
  let _searchQuery = '';

  // ========== Init ==========

  function init() {
    render();
    bindGlobalEvents();
  }

  function bindGlobalEvents() {
    // Sidebar navigation
    document.querySelector('#sidebar').addEventListener('click', (e) => {
      const navItem = e.target.closest('.sidebar-nav-item');
      if (navItem) {
        navigate(navItem.dataset.tab);
        return;
      }
    });

    // Card action delegation (like / delete)
    document.querySelector('#content').addEventListener('click', (e) => {
      const likeBtn = e.target.closest('[data-action="like"]');
      const deleteBtn = e.target.closest('[data-action="delete"]');
      if (likeBtn) {
        e.stopPropagation();
        Storage.toggleLike(likeBtn.dataset.cat, likeBtn.dataset.id);
        refresh();
      }
      if (deleteBtn) {
        e.stopPropagation();
        handleDelete(deleteBtn.dataset.cat, deleteBtn.dataset.id);
      }
    });

    // Import file
    document.querySelector('#import-file').addEventListener('change', handleImport);
  }

  // ========== Routing ==========

  function navigate(tab) {
    _currentTab = tab;
    _searchQuery = '';
    const searchInput = document.querySelector('#search-input');
    if (searchInput) searchInput.value = '';
    render();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function refresh() {
    render();
  }

  // ========== Render ==========

  function render() {
    const stats = Storage.getStats();

    // Sidebar
    document.querySelector('#sidebar').innerHTML = Components.renderSidebar(_currentTab, stats);

    // Content
    const content = document.querySelector('#content');

    if (_currentTab === 'home') {
      content.innerHTML = `
        ${Components.renderHomeHero()}
        <div class="card-grid" id="card-container">
          ${Components.renderHomeContent()}
        </div>
      `;
    } else {
      content.innerHTML = `
        ${Components.renderSearchBar()}
        <div class="card-grid" id="card-container"></div>
      `;
      const items = Storage.search(_currentTab, _searchQuery);
      document.querySelector('#card-container').innerHTML = Components.renderCardGrid(items, _currentTab);
    }
  }

  // ========== Modal ==========

  function openCreateModal() {
    if (_currentTab === 'home') {
      Components.showToast('请先选择一个分类再发布', 'info');
      return;
    }
    closeModal();
    document.body.insertAdjacentHTML('beforeend', Components.renderCreateModal(_currentTab));
    document.querySelector('#create-modal').addEventListener('click', (e) => {
      if (e.target.id === 'create-modal') closeModal();
    });
  }

  function openDetail(category, id) {
    const item = Storage.getById(category, id);
    if (!item) return;
    closeModal();
    document.body.insertAdjacentHTML('beforeend', Components.renderDetail(item, category));
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

    Storage.compressImage(file)
      .then(result => {
        _pendingImage = result.base64;
        preview.querySelector('img').src = result.base64;
        preview.style.display = 'block';
        placeholder.style.display = 'none';
        status.textContent = `图片已就绪 (${Math.round(result.base64.length / 1024)}KB)`;
        status.className = 'upload-status success';
      })
      .catch(err => {
        status.textContent = err.message;
        status.className = 'upload-status error';
        input.value = '';
      });
  }

  function clearImagePreview() {
    _pendingImage = null;
    const preview = document.querySelector('#image-preview');
    const placeholder = document.querySelector('.upload-placeholder');
    const input = document.querySelector('#image-input');
    const status = document.querySelector('#upload-status');
    if (preview) preview.style.display = 'none';
    if (placeholder) placeholder.style.display = 'flex';
    if (input) input.value = '';
    if (status) { status.textContent = '';
      status.className = 'upload-status'; }
  }

  function handleCreate(event, category) {
    event.preventDefault();
    const form = event.target;
    const submitBtn = form.querySelector('#submit-btn');
    submitBtn.disabled = true;
    submitBtn.textContent = '发布中...';

    const formData = new FormData(form);
    const tags = formData.get('tags')
      ? formData.get('tags').split(/[,，]/).map(t => t.trim()).filter(Boolean)
      : [];

    const data = { title: formData.get('title').trim(), tags };

    if (category === 'reflections') {
      data.content = formData.get('content').trim();
    } else {
      data.desc = formData.get('desc')?.trim() || '';
      if (_pendingImage) data.image = _pendingImage;
    }
    if (category === 'screenshots') {
      data.game = formData.get('game')?.trim() || '';
    }

    try {
      Storage.create(category, data);
      _pendingImage = null;
      closeModal();
      refresh();
      Components.showToast('发布成功');
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
      refresh();
      Components.showToast('已删除');
    }
  }

  function handleSearch(query) {
    _searchQuery = query;
    const items = Storage.search(_currentTab, query);
    const container = document.querySelector('#card-container');
    if (container) {
      container.innerHTML = Components.renderCardGrid(items, _currentTab);
    }
  }

  // ========== Export / Import ==========

  function handleExport() {
    const data = Storage.exportAll();
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `PriesteGamingSpace_backup_${new Date().toISOString().slice(0, 10)}.json`;
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
          Components.showToast('导入成功');
          refresh();
        } else {
          Components.showToast('文件格式不正确', 'error');
        }
      } catch {
        Components.showToast('文件解析失败', 'error');
      }
    };
    reader.readAsText(file);
    event.target.value = '';
  }

  // ========== Public API ==========
  return {
    init, navigate, refresh,
    openDetail, openCreateModal, closeModal,
    handleCreate, handleDelete, handleSearch,
    handleImagePreview, clearImagePreview,
    handleExport, handleImport
  };
})();

document.addEventListener('DOMContentLoaded', () => App.init());
