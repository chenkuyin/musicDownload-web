class MusicDownloaderApp {
    constructor() {
        this.searchResults = [];
        this.sources = [];
        this.defaultSources = ['KuwoMusicClient', 'KugouMusicClient'];
        this.downloadDir = '';
    }

    async init() {
        await this.loadSources();
        this.bindEvents();
    }

    async loadSources() {
        try {
            console.log('开始加载音乐源...');
            const response = await fetch('/sources');
            console.log('响应状态:', response.status);
            const data = await response.json();
            console.log('音乐源数据:', data);
            this.sources = data.sources || [];
            this.renderSources();
        } catch (error) {
            console.error('加载音乐源失败:', error);
        }
    }

    renderSources() {
        const container = document.getElementById('sourceChips');
        container.innerHTML = this.sources.map(source => `
            <div class="chip ${this.defaultSources.includes(source.id) ? 'active' : ''}" 
                 data-id="${source.id}"
                 onclick="app.toggleSource(this)">
                <input type="checkbox" 
                       value="${source.id}" 
                       ${this.defaultSources.includes(source.id) ? 'checked' : ''}>
                <span>${source.name}</span>
            </div>
        `).join('');
    }

    toggleSource(element) {
        const checkbox = element.querySelector('input[type="checkbox"]');
        const isActive = element.classList.contains('active');
        
        if (isActive) {
            element.classList.remove('active');
            checkbox.checked = false;
        } else {
            element.classList.add('active');
            checkbox.checked = true;
        }
    }

    bindEvents() {
        document.getElementById('searchBtn').addEventListener('click', () => this.handleSearch());
        
        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.handleSearch();
            }
        });

        document.getElementById('selectAllBtn').addEventListener('click', () => this.toggleSelectAll());
        document.getElementById('downloadSelectedBtn').addEventListener('click', () => this.downloadSelected());
        document.getElementById('browseDirBtn').addEventListener('click', () => this.browseDirectory());
    }

    async browseDirectory() {
        try {
            if ('showDirectoryPicker' in window) {
                const dirHandle = await window.showDirectoryPicker();
                this.downloadDir = dirHandle.name;
                document.getElementById('downloadDir').value = this.downloadDir;
            } else {
                const input = document.createElement('input');
                input.type = 'file';
                input.webkitdirectory = true;
                input.onchange = (e) => {
                    if (e.target.files.length > 0) {
                        this.downloadDir = e.target.files[0].webkitRelativePath.split('/')[0];
                        document.getElementById('downloadDir').value = this.downloadDir || '已选择文件夹';
                    }
                };
                input.click();
            }
        } catch (error) {
            console.log('目录选择取消或不支持');
        }
    }

    getSelectedSources() {
        const sources = [];
        const checkboxes = document.querySelectorAll('#sourceChips input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            if (checkbox.checked) {
                sources.push(checkbox.value);
            }
        });
        return sources;
    }

    async handleSearch() {
        const keyword = document.getElementById('searchInput').value.trim();
        
        if (!keyword) {
            this.showToast('请输入搜索关键词', 'error');
            return;
        }

        const sources = this.getSelectedSources();
        if (sources.length === 0) {
            this.showToast('请至少选择一个音乐源', 'error');
            return;
        }

        this.showLoading('正在搜索音乐...');
        
        try {
            console.log('发送搜索请求:', { keyword, sources });
            const response = await fetch('/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    keyword: keyword,
                    sources: sources
                })
            });

            console.log('搜索响应状态:', response.status);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '搜索请求失败');
            }

            const data = await response.json();
            console.log('搜索结果:', data);
            
            if (data.success) {
                this.searchResults = data.results;
                this.renderSearchResults();
                this.showToast(`找到 ${data.count} 首歌曲`, 'success');
            } else {
                throw new Error(data.detail || '搜索失败');
            }
        } catch (error) {
            console.error('搜索错误:', error);
            this.showToast('搜索失败: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }

    renderSearchResults() {
        const resultsList = document.getElementById('resultsList');
        const emptyState = document.getElementById('emptyState');

        if (this.searchResults.length === 0) {
            resultsList.innerHTML = '';
            resultsList.appendChild(emptyState);
            emptyState.querySelector('p').textContent = '未找到相关歌曲';
            document.getElementById('selectAllBtn').disabled = true;
            document.getElementById('downloadSelectedBtn').disabled = true;
            return;
        }

        resultsList.innerHTML = this.searchResults.map((song, index) => `
            <div class="song-item" data-index="${index}">
                <div class="song-checkbox">
                    <input type="checkbox" id="song-${index}" class="song-check">
                </div>
                <div class="song-cover">
                    ${song.cover_url ? 
                        `<img src="${song.cover_url}" alt="封面" onerror="this.parentElement.innerHTML='🎵'">` : 
                        '🎵'}
                </div>
                <div class="song-info">
                    <div class="song-name" title="${song.song_name}">${song.song_name}</div>
                    <div class="song-singer" title="${song.singers}">${song.singers}</div>
                </div>
                <div class="song-meta">
                    <span class="song-format">${song.ext || 'MP3'}</span>
                    <span>${song.source}</span>
                </div>
                <div class="song-actions">
                    <button class="btn-download" onclick="app.downloadSingle(${index})">
                        ⬇️ 下载
                    </button>
                </div>
            </div>
        `).join('');

        document.getElementById('selectAllBtn').disabled = false;
        document.getElementById('downloadSelectedBtn').disabled = false;
    }

    toggleSelectAll() {
        const checkboxes = document.querySelectorAll('.song-check');
        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        
        checkboxes.forEach(checkbox => {
            checkbox.checked = !allChecked;
        });

        const btn = document.getElementById('selectAllBtn');
        btn.textContent = allChecked ? '全选' : '取消全选';
    }

    async downloadSelected() {
        const selectedSongs = this.getSelectedSongs();
        
        if (selectedSongs.length === 0) {
            this.showToast('请先选择要下载的歌曲', 'error');
            return;
        }

        this.showLoading(`正在下载 ${selectedSongs.length} 首歌曲...`);

        let successCount = 0;
        for (let i = 0; i < selectedSongs.length; i++) {
            try {
                await this.downloadSong(selectedSongs[i], i + 1, selectedSongs.length);
                successCount++;
            } catch (error) {
                console.error(`下载失败:`, error);
            }
        }

        this.hideLoading();
        
        if (successCount > 0) {
            this.showToast(`成功下载 ${successCount}/${selectedSongs.length} 首歌曲`, successCount === selectedSongs.length ? 'success' : 'info');
        } else {
            this.showToast('所有歌曲下载失败', 'error');
        }
    }

    async downloadSingle(index) {
        const song = this.searchResults[index];
        this.showLoading(`正在下载: ${song.song_name}`);

        try {
            await this.downloadSong(song, 1, 1);
            this.showToast('下载成功！文件已从服务器删除', 'success');
        } catch (error) {
            console.error('下载错误:', error);
            this.showToast('下载失败: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }

    async downloadSong(song, current, total) {
        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    identifier: song.identifier,
                    source: song.source,
                    song_name: song.song_name,
                    singers: song.singers,
                    album: song.album,
                    ext: song.ext || 'mp3',
                    download_url: song.download_url,
                    cover_url: song.cover_url,
                    duration: song.duration,
                    file_size: song.file_size
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '创建下载任务失败');
            }

            const data = await response.json();
            
            if (data.success) {
                await this.waitForDownloadAndStream(data.task_id, song);
            } else {
                throw new Error(data.detail || '下载失败');
            }
        } catch (error) {
            throw error;
        }
    }

    async waitForDownloadAndStream(taskId, song, allowRetry = true) {
        const maxAttempts = 120;
        
        for (let i = 0; i < maxAttempts; i++) {
            try {
                const response = await fetch(`/download/${taskId}`);
                const task = await response.json();

                if (task.status === 'completed') {
                    await this.streamDownloadFile(taskId, song);
                    return true;
                } else if (task.status === 'failed') {
                    if (allowRetry) {
                        const shouldRetry = await this.showRetryDialog(song, task.message);
                        if (shouldRetry) {
                            this.showLoading(`正在重新下载: ${song.song_name}`);
                            try {
                                const retryResponse = await fetch(`/download/${taskId}/retry`, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                    }
                                });
                                
                                if (!retryResponse.ok) {
                                    throw new Error('重新下载请求失败');
                                }
                                
                                const retryData = await retryResponse.json();
                                if (retryData.success) {
                                    return await this.waitForDownloadAndStream(taskId, song, false);
                                }
                            } catch (retryError) {
                                console.error('重新下载失败:', retryError);
                                throw new Error(task.message);
                            } finally {
                                this.hideLoading();
                            }
                        }
                    }
                    throw new Error(task.message);
                }

                await this.sleep(2000);
            } catch (error) {
                if (error.message && error.message.includes('失败')) {
                    throw error;
                }
                console.log(`等待下载中... (${i+1}/${maxAttempts})`);
            }
        }

        throw new Error('下载超时');
    }

    showRetryDialog(song, errorMessage) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'retry-dialog-overlay';
            overlay.innerHTML = `
                <div class="retry-dialog">
                    <div class="retry-dialog-title">下载失败</div>
                    <div class="retry-dialog-content">
                        <p>歌曲: ${song.song_name} - ${song.singers}</p>
                        <p class="retry-error">${errorMessage || '未知错误'}</p>
                    </div>
                    <div class="retry-dialog-actions">
                        <button class="retry-btn-cancel" onclick="this.closest('.retry-dialog-overlay').remove(); window._retryResult = false;">取消</button>
                        <button class="retry-btn-confirm" onclick="this.closest('.retry-dialog-overlay').remove(); window._retryResult = true;">重新下载</button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(overlay);
            
            const checkResult = setInterval(() => {
                if (window._retryResult !== undefined) {
                    clearInterval(checkResult);
                    const result = window._retryResult;
                    window._retryResult = undefined;
                    resolve(result);
                }
            }, 100);
        });
    }

    async streamDownloadFile(taskId, song) {
        try {
            const response = await fetch(`/download/${taskId}/file`);
            
            if (!response.ok) {
                throw new Error('获取下载文件失败');
            }

            const blob = await response.blob();
            
            const filename = song.song_name + ' - ' + song.singers + '.' + (song.ext || 'mp3');
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
            
        } catch (error) {
            throw error;
        }
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    getSelectedSongs() {
        const selectedSongs = [];
        const checkboxes = document.querySelectorAll('.song-check');
        
        checkboxes.forEach((checkbox, index) => {
            if (checkbox.checked) {
                selectedSongs.push(this.searchResults[index]);
            }
        });

        return selectedSongs;
    }

    showLoading(message = '加载中...') {
        const overlay = document.getElementById('loadingOverlay');
        const text = document.getElementById('loadingText');
        text.textContent = message;
        overlay.classList.add('active');
    }

    hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        overlay.classList.remove('active');
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        
        const icons = {
            success: '✅',
            error: '❌',
            info: 'ℹ️'
        };

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type]}</span>
            <span class="toast-message">${message}</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 3000);
    }
}

const app = new MusicDownloaderApp();
document.addEventListener('DOMContentLoaded', () => {
    app.init();
});
