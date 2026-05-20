/**
 * EZVIZ LAN Camera Viewer - Frontend Application
 */

const API_BASE = '/api';
let hlsInstances = {};

// --- API Functions ---

async function fetchCameras() {
    const res = await fetch(`${API_BASE}/cameras`);
    return res.json();
}

async function addCamera(data) {
    const res = await fetch(`${API_BASE}/cameras`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    return res.json();
}

async function deleteCamera(id) {
    const res = await fetch(`${API_BASE}/cameras/${id}`, {
        method: 'DELETE',
    });
    return res.json();
}

async function startStream(id) {
    const res = await fetch(`${API_BASE}/cameras/${id}/start`, {
        method: 'POST',
    });
    return res.json();
}

async function stopStream(id) {
    const res = await fetch(`${API_BASE}/cameras/${id}/stop`, {
        method: 'POST',
    });
    return res.json();
}

// --- UI Functions ---

function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function createCameraElement(camera) {
    const div = document.createElement('div');
    div.className = `camera-item ${camera.active ? 'active' : ''}`;
    div.id = `camera-${camera.id}`;

    div.innerHTML = `
        <div class="camera-header">
            <span class="camera-name">${camera.name}</span>
            <div class="camera-status">
                <span class="status-dot ${camera.active ? 'active' : ''}"></span>
                <span>${camera.active ? 'Đang phát' : 'Dừng'}</span>
            </div>
        </div>
        <div class="camera-video" id="video-container-${camera.id}">
            ${camera.active
                ? `<video id="video-${camera.id}" autoplay muted playsinline></video>`
                : `<div class="camera-placeholder">
                    <div class="icon">📷</div>
                    <p>Nhấn "Xem" để bắt đầu</p>
                </div>`
            }
        </div>
        <div class="camera-info">
            IP: ${camera.ip}:${camera.port} | Kênh: ${camera.channel} | 
            ${camera.stream_type === 1 ? 'Main (HD)' : 'Sub (SD)'}
        </div>
        <div class="camera-controls">
            ${camera.active
                ? `<button class="btn btn-danger btn-sm" onclick="handleStopStream('${camera.id}')">⏹ Dừng</button>
                   <button class="btn btn-warning btn-sm" onclick="toggleFullscreen('${camera.id}')">⛶ Toàn màn hình</button>`
                : `<button class="btn btn-success btn-sm" onclick="handleStartStream('${camera.id}')">▶ Xem</button>`
            }
            <button class="btn btn-danger btn-sm" onclick="handleDeleteCamera('${camera.id}')">🗑 Xóa</button>
        </div>
    `;

    return div;
}

function initHlsPlayer(cameraId, streamUrl) {
    const video = document.getElementById(`video-${cameraId}`);
    if (!video) return;

    // Destroy existing instance
    if (hlsInstances[cameraId]) {
        hlsInstances[cameraId].destroy();
        delete hlsInstances[cameraId];
    }

    if (Hls.isSupported()) {
        const hls = new Hls({
            liveDurationInfinity: true,
            liveBackBufferLength: 0,
            maxBufferLength: 4,
            maxMaxBufferLength: 8,
            liveSyncDurationCount: 1,
            liveMaxLatencyDurationCount: 3,
            manifestLoadingRetryDelay: 1000,
            manifestLoadingMaxRetry: 20,
            levelLoadingRetryDelay: 1000,
            levelLoadingMaxRetry: 20,
            fragLoadingRetryDelay: 1000,
            fragLoadingMaxRetry: 20,
            enableWorker: true,
            lowLatencyMode: true,
        });
        hls.loadSource(streamUrl);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
            // Seek to live edge
            if (hls.liveSyncPosition) {
                video.currentTime = hls.liveSyncPosition;
            }
            video.play().catch(() => {});
        });
        hls.on(Hls.Events.ERROR, (event, data) => {
            if (data.fatal) {
                console.error('HLS fatal error:', data.type, data.details);
                if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
                    setTimeout(() => {
                        hls.startLoad();
                    }, 2000);
                } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
                    hls.recoverMediaError();
                }
            }
        });
        // Periodically seek to live edge to avoid falling behind
        const liveSync = setInterval(() => {
            if (video.paused) return;
            if (hls.liveSyncPosition && (hls.liveSyncPosition - video.currentTime > 3)) {
                video.currentTime = hls.liveSyncPosition;
            }
        }, 5000);
        hls._liveSyncInterval = liveSync;
        hlsInstances[cameraId] = hls;
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        // Safari native HLS support
        video.src = streamUrl;
        video.addEventListener('loadedmetadata', () => {
            video.play().catch(() => {});
        });
    }
}

async function renderCameras() {
    const grid = document.getElementById('cameraGrid');
    const cameras = await fetchCameras();

    if (cameras.length === 0) {
        grid.innerHTML = '<p class="empty-state">Chưa có camera nào. Hãy thêm camera ở trên.</p>';
        return;
    }

    grid.innerHTML = '';
    cameras.forEach(camera => {
        const el = createCameraElement(camera);
        grid.appendChild(el);

        // Initialize HLS player if stream is active
        if (camera.active && camera.stream_url) {
            setTimeout(() => initHlsPlayer(camera.id, camera.stream_url), 100);
        }
    });
}

// --- Event Handlers ---

async function handleStartStream(id) {
    showToast('Đang kết nối camera...', 'success');
    try {
        const result = await startStream(id);
        if (result.stream_url) {
            showToast('Đã kết nối thành công!', 'success');
            await renderCameras();
        }
    } catch (err) {
        showToast('Lỗi kết nối camera. Kiểm tra IP và mật khẩu.', 'error');
    }
}

async function handleStopStream(id) {
    await stopStream(id);
    if (hlsInstances[id]) {
        if (hlsInstances[id]._liveSyncInterval) {
            clearInterval(hlsInstances[id]._liveSyncInterval);
        }
        hlsInstances[id].destroy();
        delete hlsInstances[id];
    }
    showToast('Đã dừng stream', 'success');
    await renderCameras();
}

async function handleDeleteCamera(id) {
    if (!confirm('Bạn có chắc muốn xóa camera này?')) return;
    await deleteCamera(id);
    showToast('Đã xóa camera', 'success');
    await renderCameras();
}

function toggleFullscreen(id) {
    const el = document.getElementById(`camera-${id}`);
    if (el) {
        el.classList.toggle('fullscreen');
    }
}

// --- Form Handler ---

document.getElementById('addCameraForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const data = {
        name: document.getElementById('camName').value,
        ip: document.getElementById('camIp').value,
        port: parseInt(document.getElementById('camPort').value) || 554,
        username: document.getElementById('camUsername').value || 'admin',
        password: document.getElementById('camPassword').value,
        channel: parseInt(document.getElementById('camChannel').value) || 1,
        stream_type: parseInt(document.getElementById('camStreamType').value) || 1,
    };

    try {
        await addCamera(data);
        showToast(`Đã thêm camera: ${data.name}`, 'success');
        e.target.reset();
        document.getElementById('camPort').value = '554';
        document.getElementById('camUsername').value = 'admin';
        document.getElementById('camChannel').value = '1';
        await renderCameras();
    } catch (err) {
        showToast('Lỗi khi thêm camera', 'error');
    }
});

// --- Auto refresh stream status ---
setInterval(async () => {
    const cameras = await fetchCameras();
    cameras.forEach(cam => {
        const statusDot = document.querySelector(`#camera-${cam.id} .status-dot`);
        if (statusDot) {
            if (cam.active) {
                statusDot.classList.add('active');
            } else {
                statusDot.classList.remove('active');
            }
        }
    });
}, 5000);

// --- Initialize ---
renderCameras();
