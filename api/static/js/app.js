const socket = io({
    transports: ['polling']
});
const chat = document.getElementById('chat');
const inp = document.getElementById('inp');
const empty = document.getElementById('empty');
const dot = document.getElementById('dot');
const prog = document.getElementById('progBar');
const count = document.getElementById('discoveryCount');
const list = document.getElementById('deviceList');

// The server_url will be passed from index.html as a global config
const url = window.__ISODROP_CONFIG__ ? window.__ISODROP_CONFIG__.url : '';

socket.on('connect', () => {
    dot.classList.add('online');

    // Identify Device
    const ua = navigator.userAgent;
    let browser = "Unknown Browser";
    let platform = "Unknown Device";

    if (ua.includes("Firefox")) browser = "Firefox";
    else if (ua.includes("Chrome")) browser = "Chrome";
    else if (ua.includes("Safari")) browser = "Safari";
    else if (ua.includes("Edge")) browser = "Edge";

    if (ua.includes("Win")) platform = "Windows PC";
    else if (ua.includes("Mac")) platform = "Mac";
    else if (ua.includes("Android")) platform = "Android Phone";
    else if (ua.includes("iPhone")) platform = "iPhone";
    else if (ua.includes("Linux")) platform = "Linux PC";

    socket.emit('identify', {
        name: `${browser} on ${platform}`,
        platform: platform
    });
});
socket.on('disconnect', () => dot.classList.remove('online'));

socket.on('new_message', (msg) => {
    if (empty) empty.style.display = 'none';
    addMsg(msg);
    chat.scrollTop = chat.scrollHeight;
});

socket.on('load_history', (h) => {
    if (h && h.length > 0) {
        if (empty) empty.style.display = 'none';
        chat.innerHTML = ''; // Clear existing to prevent loops
        h.forEach(addMsg);
        chat.scrollTop = chat.scrollHeight;
    }
});

socket.on('history_cleared', () => location.reload());

socket.on('user_update', (users) => {
    if (!count || !list) return;
    count.innerText = users.length;
    list.innerHTML = users.map(u => {
        const isMobile = /iphone|android|ipad/.test(u.platform.toLowerCase());
        const icon = isMobile
            ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"></rect><line x1="12" y1="18" x2="12" y2="18"></line></svg>'
            : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>';

        return `
            <div class="device-item">
                <div class="device-avatar">${icon}</div>
                <div class="device-info">
                    <div class="device-name">${u.name}</div>
                    <div class="device-status">Active Now</div>
                </div>
            </div>
        `;
    }).join('');
});

function addMsg(msg) {
    const div = document.createElement('div');
    div.className = `msg ${msg.type === 'file' ? 'received' : 'sent'}`;
    if (msg.type === 'text') {
        div.textContent = msg.content;
        if (msg.content.match(/^https?:\/\//)) {
            div.innerHTML = `<a href="${msg.content}" target="_blank" style="color:inherit; text-decoration:underline;">${msg.content}</a>`;
        }
    } else {
        const ext = msg.filename.split('.').pop().toUpperCase();
        div.innerHTML = `
            <div class="file-box">
                <div class="file-icon">${ext.slice(0, 3)}</div>
                <div style="flex:1; overflow:hidden;">
                    <strong style="display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${msg.filename}</strong>
                    <small style="color:var(--text-muted)">${fSize(msg.size)}</small>
                </div>
                <a href="/download/${msg.file_id}" class="btn-save" target="_blank">SAVE</a>
            </div>
        `;
    }
    chat.appendChild(div);
}

function send() {
    if (!inp) return;
    const val = inp.value.trim();
    if (val) {
        socket.emit('send_message', { content: val });
        inp.value = '';
    }
}

if (inp) {
    inp.addEventListener('keypress', (e) => { if (e.key === 'Enter') send(); });
}

function hFiles(files) {
    if (!files.length) return;
    Array.from(files).forEach(f => {
        const d = new FormData();
        d.append('file', f);
        if (prog) prog.style.width = '20%';
        fetch('/upload', { method: 'POST', body: d })
            .then(r => r.json())
            .then(() => { if (prog) { prog.style.width = '100%'; setTimeout(() => prog.style.width = '0', 500); } })
            .catch(() => { if (prog) { prog.style.width = '0'; alert('Fail'); } });
    });
}

function toggleOverlay(type) {
    const ov = document.getElementById(type + 'Overlay');
    if (!ov) return;
    const isOpen = ov.style.display === 'flex';
    document.querySelectorAll('.overlay').forEach(o => o.style.display = 'none');
    ov.style.display = isOpen ? 'none' : 'flex';
}

function copyUrl() {
    const btn = document.querySelector('.btn-icon[title="Copy Hub URL"]');
    const oldSvg = btn.innerHTML;

    const success = () => {
        btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#55efc4" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        btn.style.borderColor = '#55efc4';
        setTimeout(() => {
            btn.innerHTML = oldSvg;
            btn.style.borderColor = '';
        }, 1500);
    };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(url).then(success);
    } else {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand("copy");
            success();
        } catch (err) {
            console.error("Fallback copy failed", err);
            alert("Copy failed. Please manually copy: " + url);
        }
        document.body.removeChild(ta);
    }
}

function resetHub() {
    if (confirm('Clear all messages and files?')) socket.emit('clear_history');
}

function manualDisconnect() {
    socket.disconnect();
    alert('Disconnected from Hub.');
    location.reload();
}

function fSize(b) {
    if (b === 0) return '0 B';
    const k = 1024, s = ['B', 'KB', 'MB', 'GB'], i = Math.floor(Math.log(b) / Math.log(k));
    return parseFloat((b / Math.pow(k, i)).toFixed(1)) + ' ' + s[i];
}

// Drag Drop logic
const area = document.getElementById('dropArea');
const zone = document.getElementById('dragZone');
if (area && zone) {
    ['dragenter', 'dragover'].forEach(e => area.addEventListener(e, (ev) => { ev.preventDefault(); zone.style.display = 'flex'; }));
    ['dragleave', 'drop'].forEach(e => area.addEventListener(e, (ev) => { ev.preventDefault(); zone.style.display = 'none'; }));
    area.addEventListener('drop', (e) => { e.preventDefault(); hFiles(e.dataTransfer.files); });
}

// Global functions for HTML access
window.send = send;
window.hFiles = hFiles;
window.toggleOverlay = toggleOverlay;
window.copyUrl = copyUrl;
window.resetHub = resetHub;
window.manualDisconnect = manualDisconnect;

// PWA Execution
const pwaBubble = document.getElementById('pwaBubble');
const iosInst = document.getElementById('ios-inst');
const chromeInst = document.getElementById('chrome-inst');
const otherInst = document.getElementById('other-inst');
const nativeBtn = document.getElementById('nativeInstallPrompt');
let deferredPrompt;

const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;

if (!isStandalone) {
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    const isChrome = /Chrome/.test(navigator.userAgent) && /Google Inc/.test(navigator.vendor);

    if (pwaBubble) pwaBubble.style.display = 'flex';

    if (isIOS) {
        if (iosInst) iosInst.style.display = 'block';
        if (otherInst) otherInst.style.display = 'none';
    } else if (isChrome || ('BeforeInstallPromptEvent' in window)) {
        if (chromeInst) chromeInst.style.display = 'block';
        if (otherInst) otherInst.style.display = 'none';
    }
}

if (inp && pwaBubble) {
    inp.addEventListener('focus', () => { pwaBubble.style.display = 'none'; });
}

if (nativeBtn) {
    nativeBtn.onclick = () => {
        console.log('Install button clicked, deferredPrompt:', !!deferredPrompt);
        if (deferredPrompt) {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then((choice) => {
                console.log('User choice outcome:', choice.outcome);
                if (choice.outcome === 'accepted') {
                    toggleOverlay('install');
                    if (pwaBubble) pwaBubble.style.display = 'none';
                }
                deferredPrompt = null;
                nativeBtn.innerText = "Install Now";
            });
        } else {
            console.warn('deferredPrompt is null. PWA criteria might not be met.');
            nativeBtn.innerText = "Still Preparing... (Try again in 5s)";
            setTimeout(() => nativeBtn.innerText = "Install Now", 2000);
        }
    };
}

window.addEventListener('beforeinstallprompt', (e) => {
    console.log('✅ PWA: beforeinstallprompt event fired');
    e.preventDefault();
    deferredPrompt = e;
    if (nativeBtn) nativeBtn.innerText = "Install Now";
});

// Register Service Worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').then(reg => {
            console.log('✅ PWA: Service Worker Registered', reg);
        }).catch(err => {
            console.log('❌ PWA: Service Worker Registration failed', err);
        });
    });
}
