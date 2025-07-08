// Save this as static/script.js
document.addEventListener('DOMContentLoaded', () => {
    // --- Global Elements & State ---
    const tabButtons = document.querySelectorAll('header .tab-button');
    const statusMessage = document.getElementById('status-message');
    let currentSearchPage = 1, currentSearchQuery = '', currentSearchType = 'song';
    let settings = {};

    // --- TEMPLATES for options panels ---
    const songOptionsHTML = `<div class="options-panel">
        <div class="option-group"><label for="song-format">Format</label><select id="song-format" data-setting="song.format"><option value="flac">FLAC</option><option value="mp3">MP3</option><option value="m4a">M4A</option></select></div>
        <div class="option-group"><label for="song-quality">Quality</label><select id="song-quality" data-setting="song.quality"><option value="0">Best</option><option value="5">Good</option><option value="9">Low</option></select></div>
        <div class="option-group toggle-group"><label>Metadata</label><label class="switch"><input type="checkbox" id="song-metadata" data-setting="song.metadata" checked><span class="slider"></span></label></div>
        <div class="option-group toggle-group"><label>Thumbnail</label><label class="switch"><input type="checkbox" id="song-thumbnail" data-setting="song.thumbnail" checked><span class="slider"></span></label></div>
    </div>`;
    
    const videoOptionsHTML = `<div class="options-panel">
        <div class="option-group"><label for="video-format">Format</label><select id="video-format" data-setting="video.format"><option value="mp4">MP4</option><option value="mkv">MKV</option></select></div>
        <div class="option-group"><label for="video-resolution">Resolution</label><select id="video-resolution" data-setting="video.resolution"><option value="1080">1080p</option><option value="720">720p</option><option value="480">480p</option></select></div>
        <div class="option-group toggle-group"><label>Include Audio</label><label class="switch"><input type="checkbox" id="video-audio" data-setting="video.audio" checked><span class="slider"></span></label></div>
    </div>`;

    // --- Settings & Persistence Logic ---
    function saveSettings() {
        localStorage.setItem('ytsp_settings', JSON.stringify(settings));
    }

    function loadSettings() {
        const savedSettings = JSON.parse(localStorage.getItem('ytsp_settings'));
        settings = Object.assign({
            song: { format: 'flac', quality: '0', metadata: true, thumbnail: true },
            video: { format: 'mp4', resolution: '1080', audio: true }
        }, savedSettings);

        document.getElementById('music-options').innerHTML = songOptionsHTML;
        document.getElementById('video-options').innerHTML = videoOptionsHTML;
        document.getElementById('song-settings-view').innerHTML = songOptionsHTML.replaceAll(' id="song-', ' id="search-song-');
        document.getElementById('video-settings-view').innerHTML = videoOptionsHTML.replaceAll(' id="video-', ' id="search-video-');
        
        document.querySelectorAll('[data-setting]').forEach(el => {
            const keys = el.dataset.setting.split('.');
            const value = settings[keys[0]][keys[1]];
            el.type === 'checkbox' ? el.checked = value : el.value = value;
            el.addEventListener('change', (e) => {
                const newValue = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
                settings[keys[0]][keys[1]] = newValue;
                saveSettings();
                document.querySelectorAll(`[data-setting="${el.dataset.setting}"]`).forEach(syncEl => {
                    if (syncEl !== el) { syncEl.type === 'checkbox' ? syncEl.checked = newValue : syncEl.value = newValue; }
                });
            });
        });
    }

    // --- Initialization ---
    loadSettings();

    // --- Tab Switching Logic ---
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            document.querySelector('header .tab-button.active').classList.remove('active');
            button.classList.add('active');
            document.querySelectorAll('main > .view').forEach(view => {
                view.id === button.dataset.view ? view.classList.add('active') : view.classList.remove('active');
            });
            if (button.dataset.view === 'files-view') fetchFiles();
        });
    });

    // --- Real-Time Download Logic ---
    async function triggerDownload(url, options, button) {
        button.disabled = true;
        button.classList.add('downloading');
        const progressBar = button.querySelector('.progress-bar');
        const buttonText = button.querySelector('span');
        progressBar.style.width = '0%';
        try {
            const response = await fetch('/start-download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, options }),
            });
            const result = await response.json();
            if (!result.success) throw new Error(result.error || 'Failed to start download on server.');
            
            const eventSource = new EventSource(`/progress/${result.task_id}`);
            eventSource.onmessage = (event) => { progressBar.style.width = `${event.data}%`; };
            eventSource.addEventListener('done', () => {
                progressBar.style.width = '100%';
                button.classList.remove('downloading');
                button.classList.add('downloaded');
                buttonText.textContent = 'Done ✓';
                eventSource.close();
                if (document.getElementById('files-view').classList.contains('active')) fetchFiles();
            });
            eventSource.addEventListener('error', (event) => { throw new Error(event.data || 'Download failed on server.'); });
        } catch (err) {
            button.classList.remove('downloading');
            button.classList.add('error');
            buttonText.textContent = 'Error ✗';
            statusMessage.textContent = `Error: ${err.message}`;
            setTimeout(() => {
                button.disabled = false;
                button.classList.remove('error');
                progressBar.style.width = '0%';
                buttonText.textContent = 'Download';
            }, 5000);
        }
    }

    // --- Downloader View ---
    const urlInput = document.getElementById('url-input');
    urlInput.addEventListener('input', () => {
        const url = urlInput.value.trim().toLowerCase();
        document.getElementById('music-options').classList.toggle('hidden', !(url.includes('spotify') || url.includes('music.youtube')));
        document.getElementById('video-options').classList.toggle('hidden', !(url.includes('youtube.com/watch') || url.includes('youtu.be')));
    });

    document.getElementById('download-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (!url) return;
        const options = url.includes('spotify') || url.includes('music.youtube') ? settings.song : settings.video;
        triggerDownload(url, options, e.target.querySelector('button'));
    });

    // --- Search View ---
    const searchForm = document.getElementById('search-form');
    searchForm.addEventListener('submit', (e) => {
        e.preventDefault();
        currentSearchQuery = document.getElementById('search-input').value.trim();
        currentSearchType = document.getElementById('search-type-toggle').checked ? 'video' : 'song';
        currentSearchPage = 1;
        if (currentSearchQuery) fetchSearchResults();
    });
    
    async function fetchSearchResults() {
        const resultsContainer = document.getElementById('search-results-container');
        resultsContainer.innerHTML = '<div id="loader" class="centered-loader"></div>';
        try {
            const data = await (await fetch(`/api/search?q=${encodeURIComponent(currentSearchQuery)}&type=${currentSearchType}&page=${currentSearchPage}`)).json();
            resultsContainer.innerHTML = '';
            if (data.results?.length) {
                renderSearchResults(data.results);
                renderPagination(data.page, data.has_next);
            } else { resultsContainer.innerHTML = '<p>No results found.</p>'; }
        } catch (err) { resultsContainer.innerHTML = '<p>Search failed.</p>'; }
    }

    function renderSearchResults(results) {
        const resultsContainer = document.getElementById('search-results-container');
        results.forEach(item => {
            const el = document.createElement('div');
            el.className = 'search-result';
            el.innerHTML = `<img src="/api/thumbnail?url=${encodeURIComponent(item.thumbnail)}" alt="" class="thumbnail" onerror="this.style.display='none'"><div class="info"><div class="title">${item.title}</div><div class="author">${item.author}</div></div><button class="download-btn-small"><div class="progress-bar"></div><span>Download</span></button>`;
            el.querySelector('.download-btn-small').addEventListener('click', (e) => {
                const downloadOptions = currentSearchType === 'song' ? settings.song : settings.video;
                triggerDownload(item.url, downloadOptions, e.currentTarget);
            });
            resultsContainer.appendChild(el);
        });
    }

    function renderPagination(page, hasNext) {
        const paginationContainer = document.getElementById('search-pagination');
        paginationContainer.innerHTML = '';
        if (page > 1) paginationContainer.appendChild(Object.assign(document.createElement('button'), { textContent: 'Previous', onclick: () => { currentSearchPage--; fetchSearchResults(); } }));
        if (hasNext && page < 3) paginationContainer.appendChild(Object.assign(document.createElement('button'), { textContent: 'Next', onclick: () => { currentSearchPage++; fetchSearchResults(); } }));
    }

    // --- Settings Modal Logic ---
    const settingsOverlay = document.getElementById('settings-overlay');
    document.getElementById('search-settings-btn').addEventListener('click', () => settingsOverlay.classList.remove('hidden'));
    document.getElementById('settings-close-btn').addEventListener('click', () => settingsOverlay.classList.add('hidden'));
    settingsOverlay.addEventListener('click', (e) => { if (e.target === settingsOverlay) settingsOverlay.classList.add('hidden'); });

    document.querySelectorAll('#settings-tabs .settings-tab-button').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelector('#settings-tabs .settings-tab-button.active').classList.remove('active');
            button.classList.add('active');
            document.querySelectorAll('#settings-modal .view').forEach(view => {
                view.id === button.dataset.view ? view.classList.add('active') : view.classList.remove('active');
            });
        });
    });

    // --- Files View Logic ---
    const fileBrowserContainer = document.getElementById('file-browser-container');
    const contextMenu = document.getElementById('context-menu');
    let contextFile = null;

    async function fetchFiles() {
        try {
            const files = await (await fetch('/api/files')).json();
            fileBrowserContainer.innerHTML = files.length ? '' : '<p>No files found.</p>';
            files.forEach(f => {
                const el = document.createElement('div'); el.className = 'file-item'; el.dataset.filename = f.name;
                el.innerHTML = `<div class="file-icon">${f.name.endsWith('.zip')?'Z':(f.name.match(/\\.(mp4|mkv)$/)?'V':'M')}</div><div class="file-info"><div class="file-name">${f.name}</div><div class="file-meta">${((b,d=2)=>(b===0)?'0 B':( (b,p)=>`${parseFloat((b/Math.pow(1024,p)).toFixed(d<0?0:d))} ${['B','KB','MB','GB'][p]}`)(b,Math.floor(Math.log(b)/Math.log(1024))))(f.size)}</div></div><button class="dots-menu">...</button>`;
                fileBrowserContainer.appendChild(el);
            });
        } catch (err) { fileBrowserContainer.innerHTML = '<p>Could not load files.</p>'; }
    }

    document.addEventListener('click', e => {
        if (e.target.classList.contains('dots-menu')) {
            contextFile = e.target.closest('.file-item').dataset.filename;
            contextMenu.style.left = `${e.pageX - 100}px`; contextMenu.style.top = `${e.pageY + 10}px`;
            contextMenu.classList.remove('hidden');
        } else if (!e.target.closest('#context-menu')) { contextMenu.classList.add('hidden'); }
    });

    document.getElementById('context-download').addEventListener('click', () => { if (contextFile) window.location.href = `/downloads/${encodeURIComponent(contextFile)}`; });
    document.getElementById('context-delete').addEventListener('click', async () => {
        if (contextFile && confirm(`Delete ${contextFile}?`)) {
            const res = await (await fetch('/api/delete', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ filename: contextFile }) })).json();
            if (res.success) fetchFiles(); else alert('Deletion failed: ' + res.error);
        }
    });
});
