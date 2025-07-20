// static/main.js
document.addEventListener('DOMContentLoaded', () => {
    // Firebase configuration will be loaded from environment or config file
    // For now, we'll use a fallback approach that doesn't require Firebase for basic functionality
    let db = null;
    let firebaseAvailable = false;
    
    // Try to initialize Firebase if available
    try {
        // Check if Firebase is loaded
        if (typeof firebase !== 'undefined') {
            // Firebase config should be set via environment variables in production
            // For development, you can uncomment and fill the config below:
            /*
            const firebaseConfig = {
                apiKey: "your-api-key",
                authDomain: "your-project.firebaseapp.com",
                projectId: "your-project-id",
                storageBucket: "your-project.appspot.com",
                messagingSenderId: "123456789",
                appId: "your-app-id"
            };
            firebase.initializeApp(firebaseConfig);
            */
            
            // For now, skip Firebase initialization to prevent errors
            console.log("Firebase SDK loaded but not configured. Real-time features disabled.");
        }
    } catch (e) {
        console.warn("Firebase initialization failed:", e);
        console.log("Continuing without real-time features...");
    }
    
    // Initialize Firestore if available
    if (firebaseAvailable && firebase.apps.length > 0) {
        db = firebase.firestore();
        console.log("Firestore initialized successfully");
    }

    // --- DOM Elements ---
    const guildSelect = document.getElementById('guild-select');
    const dashboardContent = document.getElementById('dashboard-content');
    const playBtn = document.getElementById('play-btn');
    const skipBtn = document.getElementById('skip-btn');
    const stopBtn = document.getElementById('stop-btn');
    const songQueryInput = document.getElementById('song-query');
    
    // --- New elements for the new design ---
    const currentTrackTitleEl = document.getElementById('current-track-title');
    const currentTrackRequesterEl = document.getElementById('current-track-requester');
    const queueListEl = document.getElementById('queue-list');

    let currentGuildId = null;
    let firestoreListener = null;
    let updateInterval = null;

    // --- Event Listeners ---
    guildSelect.addEventListener('change', () => {
        currentGuildId = guildSelect.value;
        
        // Clean up previous listeners
        if (firestoreListener) {
            firestoreListener();
            firestoreListener = null;
        }
        if (updateInterval) {
            clearInterval(updateInterval);
            updateInterval = null;
        }
        
        if (currentGuildId) {
            dashboardContent.classList.remove('hidden');
            if (db) {
                listenToPlaybackState();
            } else {
                // Fallback: poll for updates without real-time
                startPollingUpdates();
            }
        } else {
            dashboardContent.classList.add('hidden');
        }
    });
    
    playBtn.addEventListener('click', () => {
        const query = songQueryInput.value.trim();
        if (query) {
            sendCommand('play', query);
        } else {
            showMessage('กรุณาใส่ชื่อเพลงหรือลิงก์', 'error');
        }
    });
    
    skipBtn.addEventListener('click', () => sendCommand('skip'));
    stopBtn.addEventListener('click', () => sendCommand('stop'));
    songQueryInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            playBtn.click();
        }
    });

    // --- Core Functions ---
    async function sendCommand(action, payload = null) {
        if (!currentGuildId) {
            showMessage('กรุณาเลือกเซิร์ฟเวอร์ก่อน', 'error');
            return;
        }
        
        if (action === 'play' && !payload) {
            showMessage('กรุณาใส่ชื่อเพลงหรือลิงก์', 'error');
            return;
        }

        try {
            showMessage('กำลังส่งคำสั่ง...', 'info');
            
            const response = await fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    guild_id: currentGuildId, 
                    action, 
                    payload 
                }),
            });

            const result = await response.json();
            
            if (response.ok && result.status === 'success') {
                showMessage(result.message || 'ส่งคำสั่งสำเร็จ', 'success');
                if (action === 'play') {
                    songQueryInput.value = '';
                }
            } else {
                showMessage(result.message || 'เกิดข้อผิดพลาด', 'error');
            }
        } catch (error) {
            console.error('Failed to send command:', error);
            showMessage('ไม่สามารถส่งคำสั่งได้', 'error');
        }
    }

    function listenToPlaybackState() {
        if (!db) return;
        
        try {
            const stateRef = db.collection('guilds').doc(currentGuildId).collection('state').doc('playback');
            firestoreListener = stateRef.onSnapshot(doc => {
                const state = doc.exists ? doc.data() : {};
                updateUI(state);
            }, error => {
                console.error('Firestore listener error:', error);
                // Fallback to polling if real-time fails
                startPollingUpdates();
            });
        } catch (error) {
            console.error('Failed to setup Firestore listener:', error);
            startPollingUpdates();
        }
    }

    function startPollingUpdates() {
        // Basic polling fallback (every 5 seconds)
        updateInterval = setInterval(() => {
            // Since we don't have real-time updates, we'll just show static state
            updateUI({
                current_track: null,
                queue: [],
                is_paused: false
            });
        }, 5000);
    }

    function updateUI(state = {}) {
        const { current_track, queue = [], is_paused } = state;
        
        // Update player card
        if (current_track) {
            currentTrackTitleEl.textContent = current_track.title || 'Unknown Title';
            const status = is_paused ? 'หยุดชั่วคราว' : 'กำลังเล่น...';
            currentTrackRequesterEl.textContent = status;
        } else {
            currentTrackTitleEl.textContent = 'ยังไม่มีเพลงเล่น';
            currentTrackRequesterEl.textContent = 'เลือกเพลงได้เลย';
        }

        // Update queue list
        queueListEl.innerHTML = '';
        if (queue.length > 0) {
            queue.forEach((song, index) => {
                const li = document.createElement('li');
                li.textContent = `${index + 1}. ${song.title || 'Unknown Title'}`;
                queueListEl.appendChild(li);
            });
        } else {
            const li = document.createElement('li');
            li.textContent = 'คิวยังว่างอยู่';
            li.style.color = '#a0a0a0';
            li.style.fontStyle = 'italic';
            queueListEl.appendChild(li);
        }
    }

    function showMessage(message, type = 'info') {
        // Create a simple toast notification
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            z-index: 1000;
            opacity: 0;
            transition: opacity 0.3s ease;
        `;

        // Set colors based on type
        const colors = {
            success: '#4CAF50',
            error: '#f44336',
            info: '#2196F3',
            warning: '#ff9800'
        };
        toast.style.backgroundColor = colors[type] || colors.info;

        document.body.appendChild(toast);
        
        // Show toast
        setTimeout(() => toast.style.opacity = '1', 10);
        
        // Remove toast after 3 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 3000);
    }

    // Initialize UI
    updateUI();
});
