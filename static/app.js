class MusicDownloaderApp {
    constructor() {
        this.searchResults = [];
        this.init();
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        document.getElementById('searchBtn').addEventListener('click', () => this.handleSearch());
        
        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.handleSearch();
            }
        });

        document.querySelectorAll('.source-chips .chip').forEach(chip => {
            chip.addEventListener('click', () => {
                chip.classList.toggle('active');
                const checkbox = chip.querySelector('input[type="checkbox"]');
                checkbox.checked = chip.classList.contains('active');
            });
        });

        document.getElementById('selectAllBtn').addEventListener('click', () => this.toggleSelectAll());
        document.getElementById('downloadSelectedBtn').addEventListener('click', () => this.downloadSelected());
    }

    getSelectedSources() {
        const sources = [];
        document.querySelectorAll('.source-chips input[type="checkbox"]:checked').forEach(checkbox => {
            sources.push(checkbox.value);
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

            if (!response.ok) {
                throw new Error('搜索请求失败');
            }

            const data = await response.json();
            
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
                throw new Error('创建下载任务失败');
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

    async waitForDownloadAndStream(taskId, song) {
        const maxAttempts = 60;
        
        for (let i = 0; i < maxAttempts; i++) {
            try {
                const response = await fetch(`/download/${taskId}`);
                const task = await response.json();

                if (task.status === 'completed') {
                    await this.streamDownloadFile(taskId, song);
                    return true;
                } else if (task.status === 'failed') {
                    throw new Error(task.message);
                }

                await this.sleep(1000);
            } catch (error) {
                throw error;
            }
        }

        throw new Error('下载超时');
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
