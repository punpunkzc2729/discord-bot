// Modern Discord Music Dashboard JavaScript
class DiscordMusicDashboard {
    constructor() {
        this.currentGuild = null;
        this.isPlayerVisible = false;
        this.db = null;
        this.firestoreListener = null;
        this.init();
    }

    init() {
        this.initializeFirebase();
        this.setupEventListeners();
        this.checkGuildSelection();
    }

    initializeFirebase() {
        try {
            if (typeof firebase !== 'undefined') {
                console.log("Firebase SDK loaded but not configured. Real-time features disabled.");
            }
        } catch (e) {
            console.warn("Firebase initialization failed:", e);
        }
    }

    setupEventListeners() {
        // Guild selection
        const guildSelect = document.getElementById('guild-select');
        if (guildSelect) {
            guildSelect.addEventListener('change', (e) => {
                this.handleGuildChange(e.target.value);
            });
        }

        // Search functionality
        const mainSearch = document.getElementById('main-search');
        const searchBtn = document.getElementById('search-btn');

        if (searchBtn) {
            searchBtn.addEventListener('click', () => {
                this.handleSearch(mainSearch.value);
            });
        }

        if (mainSearch) {
            mainSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.handleSearch(mainSearch.value);
                }
            });
        }

        // Popular song items
        const songItems = document.querySelectorAll('.song-item');
        songItems.forEach(item => {
            const query = item.dataset.query;
            
            item.addEventListener('click', () => {
                if (query) this.handleSearch(query);
            });
        });

        // Quick action buttons
        const shuffleBtn = document.getElementById('shuffle-btn');
        const repeatBtn = document.getElementById('repeat-btn');
        const clearQueueBtn = document.getElementById('clear-queue-btn');
        
        if (shuffleBtn) {
            shuffleBtn.addEventListener('click', () => {
                this.showNotification('🔀 Shuffle mode not implemented yet', 'info');
            });
        }
        
        if (repeatBtn) {
            repeatBtn.addEventListener('click', () => {
                this.showNotification('🔁 Repeat mode not implemented yet', 'info');
            });
        }
        
        if (clearQueueBtn) {
            clearQueueBtn.addEventListener('click', () => {
                this.handleCommand('stop');
            });
        }

        // Main play button in now playing card
        const mainPlayBtn = document.getElementById('main-play-btn');
        if (mainPlayBtn) {
            mainPlayBtn.addEventListener('click', () => {
                this.togglePlayPause();
            });
        }

        // Player controls
        this.setupPlayerControls();
    }


    setupPlayerControls() {
        // Bottom player controls
        const playPauseBtn = document.getElementById('play-pause-btn');
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');
        const volumeToggle = document.getElementById('volume-toggle');
        const volumeRange = document.getElementById('volume-range');
        const queueToggle = document.getElementById('queue-toggle');

        if (playPauseBtn) {
            playPauseBtn.addEventListener('click', () => {
                this.togglePlayPause();
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                this.handleCommand('skip');
            });
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                this.showNotification('⏮️ Previous track not implemented yet', 'info');
            });
        }

        if (volumeRange) {
            volumeRange.addEventListener('input', (e) => {
                this.updateVolumeIcon(e.target.value);
            });
        }

        if (volumeToggle) {
            volumeToggle.addEventListener('click', () => {
                this.toggleMute();
            });
        }

        if (queueToggle) {
            queueToggle.addEventListener('click', () => {
                this.showNotification('📝 Queue management coming soon', 'info');
            });
        }
    }

    handleGuildChange(guildId) {
        this.currentGuild = guildId;
        
        if (guildId) {
            this.showMainContent();
            this.showPlayerControls();
            console.log(`Selected guild: ${guildId}`);
        } else {
            this.hideMainContent();
            this.hidePlayerControls();
        }
    }

    handleSearch(query) {
        if (!this.currentGuild) {
            this.showNotification('กรุณาเลือกเซิร์ฟเวอร์ก่อน', 'warning');
            return;
        }

        if (!query.trim()) {
            this.showNotification('กรุณาป้อนชื่อเพลงหรือลิงก์', 'warning');
            return;
        }

        this.showNotification('🔍 กำลังค้นหาเพลง...', 'info');
        
        this.sendCommand('play', { query: query.trim() })
            .then(response => {
                if (response.status === 'success') {
                    this.showNotification('✅ เพิ่มเพลงสำเร็จแล้ว', 'success');
                    this.clearSearchInputs();
                    this.updatePlayerInfo(query);
                } else {
                    this.showNotification(`❌ ${response.message}`, 'error');
                }
            })
            .catch(error => {
                console.error('Search error:', error);
                this.showNotification('❌ เกิดข้อผิดพลาดในการค้นหา', 'error');
            });
    }

    handleCommand(action, payload = {}) {
        if (!this.currentGuild) {
            this.showNotification('กรุณาเลือกเซิร์ฟเวอร์ก่อน', 'warning');
            return Promise.reject('No guild selected');
        }

        return this.sendCommand(action, payload);
    }

    async sendCommand(action, payload = {}) {
        try {
            const response = await fetch('/api/command', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    guild_id: this.currentGuild,
                    action: action,
                    payload: payload
                })
            });

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || 'Command failed');
            }

            return data;
        } catch (error) {
            console.error('Command error:', error);
            throw error;
        }
    }

    togglePlayPause() {
        const playPauseBtn = document.getElementById('play-pause-btn');
        const mainPlayBtn = document.getElementById('main-play-btn');
        const playIcon = playPauseBtn ? playPauseBtn.querySelector('i') : null;
        const mainIcon = mainPlayBtn ? mainPlayBtn.querySelector('i') : null;
        
        const isPlaying = playIcon && playIcon.classList.contains('fa-pause');
        
        if (isPlaying) {
            this.handleCommand('pause')
                .then(() => {
                    if (playIcon) {
                        playIcon.classList.remove('fa-pause');
                        playIcon.classList.add('fa-play');
                    }
                    if (mainIcon) {
                        mainIcon.classList.remove('fa-pause');
                        mainIcon.classList.add('fa-play');
                    }
                    this.showNotification('⏸️ Paused', 'info');
                })
                .catch(error => {
                    this.showNotification('❌ ไม่สามารถหยุดเพลงได้', 'error');
                });
        } else {
            this.handleCommand('resume')
                .then(() => {
                    if (playIcon) {
                        playIcon.classList.remove('fa-play');
                        playIcon.classList.add('fa-pause');
                    }
                    if (mainIcon) {
                        mainIcon.classList.remove('fa-play');
                        mainIcon.classList.add('fa-pause');
                    }
                    this.showNotification('▶️ Playing', 'info');
                })
                .catch(error => {
                    this.showNotification('❌ ไม่สามารถเล่นเพลงได้', 'error');
                });
        }
    }

    updateVolumeIcon(volume) {
        const volumeToggle = document.getElementById('volume-toggle');
        const volumeBtn = document.getElementById('volume-btn');
        
        const updateIcon = (btn) => {
            if (!btn) return;
            const icon = btn.querySelector('i');
            if (!icon) return;
            
            icon.classList.remove('fa-volume-off', 'fa-volume-low', 'fa-volume-high');
            
            if (volume == 0) {
                icon.classList.add('fa-volume-off');
            } else if (volume < 50) {
                icon.classList.add('fa-volume-low');
            } else {
                icon.classList.add('fa-volume-high');
            }
        };
        
        updateIcon(volumeToggle);
        updateIcon(volumeBtn);
    }

    toggleMute() {
        const volumeRange = document.getElementById('volume-range');
        if (!volumeRange) return;
        
        const currentVolume = volumeRange.value;
        
        if (currentVolume > 0) {
            volumeRange.dataset.previousVolume = currentVolume;
            volumeRange.value = 0;
        } else {
            volumeRange.value = volumeRange.dataset.previousVolume || 50;
        }
        
        this.updateVolumeIcon(volumeRange.value);
    }


    updatePlayerInfo(trackTitle) {
        // Update now playing card
        const currentTrackTitle = document.getElementById('current-track-title');
        const currentTrackArtist = document.getElementById('current-track-artist');
        
        // Update bottom player controls
        const controlsTrackTitle = document.getElementById('controls-track-title');
        const controlsTrackArtist = document.getElementById('controls-track-artist');
        
        if (currentTrackTitle) {
            currentTrackTitle.textContent = trackTitle;
        }
        
        if (currentTrackArtist) {
            currentTrackArtist.textContent = 'กำลังเล่น...';
        }
        
        if (controlsTrackTitle) {
            controlsTrackTitle.textContent = trackTitle;
        }
        
        if (controlsTrackArtist) {
            controlsTrackArtist.textContent = 'กำลังเล่น...';
        }

        // Show player controls if hidden
        this.showPlayerControls();
    }

    clearSearchInputs() {
        const mainSearch = document.getElementById('main-search');
        if (mainSearch) mainSearch.value = '';
    }

    showMainContent() {
        const mainContent = document.getElementById('main-content');
        const welcomeScreen = document.getElementById('welcome-screen');
        
        if (mainContent) {
            mainContent.style.display = 'flex';
        }
        if (welcomeScreen) {
            welcomeScreen.style.display = 'none';
        }
    }

    hideMainContent() {
        const mainContent = document.getElementById('main-content');
        const welcomeScreen = document.getElementById('welcome-screen');
        
        if (mainContent) {
            mainContent.style.display = 'none';
        }
        if (welcomeScreen) {
            welcomeScreen.style.display = 'flex';
        }
    }

    showPlayerControls() {
        const playerControls = document.getElementById('player-controls');
        if (playerControls && !this.isPlayerVisible) {
            playerControls.style.display = 'flex';
            this.isPlayerVisible = true;
        }
    }

    hidePlayerControls() {
        const playerControls = document.getElementById('player-controls');
        if (playerControls && this.isPlayerVisible) {
            playerControls.style.display = 'none';
            this.isPlayerVisible = false;
        }
    }

    checkGuildSelection() {
        const guildSelect = document.getElementById('guild-select');
        if (guildSelect && guildSelect.value) {
            this.handleGuildChange(guildSelect.value);
        }
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        // Style the notification
        Object.assign(notification.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 20px',
            borderRadius: '8px',
            color: 'white',
            fontSize: '14px',
            fontWeight: '500',
            zIndex: '10000',
            maxWidth: '300px',
            wordWrap: 'break-word',
            transition: 'all 0.3s ease'
        });

        // Set background color based on type
        const colors = {
            success: '#00d562',
            error: '#ff0000',
            warning: '#ff9500',
            info: '#3ea6ff'
        };
        notification.style.backgroundColor = colors[type] || colors.info;

        // Add to page
        document.body.appendChild(notification);

        // Auto remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.style.opacity = '0';
                notification.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    notification.remove();
                }, 300);
            }
        }, 3000);
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.musicDashboard = new DiscordMusicDashboard();
    console.log('🎵 Discord Music Dashboard initialized');
});