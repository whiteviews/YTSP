// Save this as static/script.js
document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const urlInput = document.getElementById('url-input');
    const downloadForm = document.getElementById('download-form');
    const downloadButton = document.getElementById('download-button');
    
    const musicOptionsPanel = document.getElementById('music-options');
    const videoOptionsPanel = document.getElementById('video-options');

    const statusMessage = document.getElementById('status-message');
    const loader = document.getElementById('loader');
    const downloadLink = document.getElementById('download-link');

    // --- Event Listeners ---
    urlInput.addEventListener('input', handleUrlInput);
    downloadForm.addEventListener('submit', handleFormSubmit);

    // --- Functions ---
    function handleUrlInput() {
        const url = urlInput.value.trim().toLowerCase();
        resetStatus();

        if (url.includes('music.youtube.com') || url.includes('spotify.com')) {
            videoOptionsPanel.classList.add('hidden');
            musicOptionsPanel.classList.remove('hidden');
        } else if (url.includes('youtube.com/watch') || url.includes('youtu.be/')) {
            // Check if it's NOT a playlist, or a video within a playlist
            musicOptionsPanel.classList.add('hidden');
            videoOptionsPanel.classList.remove('hidden');
        } else if (url.includes('youtube.com/playlist')) {
            // A pure playlist link should default to music options
            videoOptionsPanel.classList.add('hidden');
            musicOptionsPanel.classList.remove('hidden');
        } else {
            musicOptionsPanel.classList.add('hidden');
            videoOptionsPanel.classList.add('hidden');
        }
    }

    async function handleFormSubmit(event) {
        event.preventDefault();
        
        const url = urlInput.value.trim();
        if (!url) {
            showError("Please paste a URL first.");
            return;
        }

        startLoading();
        
        const options = {};
        if (!musicOptionsPanel.classList.contains('hidden')) {
            options.format = document.getElementById('music-format').value;
            options.quality = document.getElementById('audio-quality').value;
            options.metadata = document.getElementById('metadata-toggle').checked;
            options.thumbnail = document.getElementById('thumbnail-toggle').checked;
        } else if (!videoOptionsPanel.classList.contains('hidden')) {
            options.format = document.getElementById('video-format').value;
            options.resolution = document.getElementById('resolution').value;
            options.audio = document.getElementById('audio-toggle').checked;
        }

        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, options }),
            });

            const result = await response.json();

            if (result.success) {
                showSuccess(result.filename, result.file_url);
            } else {
                showError(result.error);
            }
        } catch (error) {
            showError('An unexpected error occurred. Check the server console.');
            console.error(error);
        } finally {
            stopLoading();
        }
    }

    function startLoading() {
        downloadButton.disabled = true;
        downloadButton.textContent = 'Processing...';
        loader.classList.remove('hidden');
        statusMessage.textContent = 'Please wait, this can take a while for playlists...';
        statusMessage.className = '';
        downloadLink.classList.add('hidden');
    }

    function stopLoading() {
        downloadButton.disabled = false;
        downloadButton.textContent = 'Download';
        loader.classList.add('hidden');
    }

    function resetStatus() {
        statusMessage.textContent = '';
        statusMessage.className = '';
        downloadLink.classList.add('hidden');
        downloadLink.href = '#';
    }

    function showError(message) {
        statusMessage.textContent = `Error: ${message}`;
        statusMessage.className = 'error';
    }

    function showSuccess(filename, url) {
        statusMessage.textContent = 'Download ready!';
        statusMessage.className = 'success';
        downloadLink.href = url;
        downloadLink.textContent = `Download ${filename}`;
        downloadLink.classList.remove('hidden');
    }
});
