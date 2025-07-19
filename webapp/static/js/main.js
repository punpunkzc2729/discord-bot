// webapp/static/js/main.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Firebase Configuration ---
    // IMPORTANT: Replace with your web app's Firebase config from your Firebase project settings.
    const firebaseConfig = {
        apiKey: "YOUR_API_KEY",
        authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
        projectId: "YOUR_PROJECT_ID",
        storageBucket: "YOUR_PROJECT_ID.appspot.com",
        messagingSenderId: "YOUR_SENDER_ID",
        appId: "YOUR_APP_ID"
    };

    // Initialize Firebase
    try {
        if (firebase.apps.length === 0) {
            firebase.initializeApp(firebaseConfig);
        }
    } catch (e) {
        console.error("Firebase initialization error:", e);
        alert("Could not initialize Firebase. Please check your configuration.");
        return;
    }
    
    const db = firebase.firestore();

    // --- DOM Elements ---
    const guildSelect = document.getElementById('guild-select');
    const dashboardContent = document.getElementById('dashboard-content');
    const playBtn = document.getElementById('play-btn');
    const pauseBtn = document.getElementById('pause-btn');
    const resumeBtn = document.getElementById('resume-btn');
    const skipBtn = document.getElementById('skip-btn');
    const stopBtn = document.getElementById('stop-btn');
    const songQueryInput = document.getElementById('song-query');
    const currentTrackEl = document.getElementById('current-track');
    const queueListEl = document.getElementById('queue-list');

    let currentGuildId = null;
    let firestoreListener = null; // To hold the active listener

    // --- Event Listeners ---
    guildSelect.addEventListener('change', () => {
        currentGuildId = guildSelect.value;
        if (currentGuildId) {
            dashboardContent.classList.remove('hidden');
            listenToPlaybackState();
        } else {
            dashboardContent.classList.add('hidden');
            // Detach the old listener if a server is deselected
            if (firestoreListener) {
                firestoreListener(); 
                firestoreListener = null;
            }
        }
    });
    
    // Assign button clicks to send commands
    playBtn.addEventListener('click', () => {
        if (songQueryInput.value.trim()) {
            sendCommand('play', songQueryInput.value.trim());
        }
    });
    pauseBtn.addEventListener('click', () => sendCommand('pause'));
    resumeBtn.addEventListener('click', () => sendCommand('resume')); 
    skipBtn.addEventListener('click', () => sendCommand('skip'));
    stopBtn.addEventListener('click', () => sendCommand('stop'));

    // Allow pressing Enter in the input box to trigger play
    songQueryInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault(); // Prevent form submission
            playBtn.click();
        }
    });


    // --- Core Functions ---
    /**
     * Sends a command to the Flask backend API.
     * @param {string} action The command to perform (e.g., 'play', 'pause').
     * @param {string|null} payload The data for the command (e.g., song query).
     */
    async function sendCommand(action, payload = null) {
        if (!currentGuildId) {
            alert('Please select a server first.');
            return;
        }

        try {
            const response = await fetch('/api/command', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    guild_id: currentGuildId,
                    action: action,
                    payload: payload,
                }),
            });

            const result = await response.json();
            if (result.status !== 'success') {
                alert(`Error: ${result.message}`);
            } else {
                // Clear input after successfully sending a play command
                if (action === 'play') {
                    songQueryInput.value = '';
                }
            }
        } catch (error) {
            console.error('Failed to send command:', error);
            alert('An error occurred while sending the command.');
        }
    }

    /**
     * Listens for real-time updates to the playback state in Firestore
     * for the currently selected guild.
     */
    function listenToPlaybackState() {
        // Detach any existing listener before creating a new one
        if (firestoreListener) {
            firestoreListener();
        }

        const stateRef = db.collection('guilds').doc(currentGuildId).collection('state').doc('playback');
        
        firestoreListener = stateRef.onSnapshot(doc => {
            if (doc.exists) {
                const data = doc.data();
                updateUI(data);
            } else {
                // Reset UI if no state document exists (e.g., bot just started)
                updateUI({ current_track: null, queue: [], is_playing: false, is_paused: false });
            }
        }, err => {
            console.error('Firestore listener error:', err);
            // Optionally reset UI on error
            updateUI({ current_track: null, queue: [], is_playing: false, is_paused: false });
        });
    }

    /**
     * Updates the web dashboard UI based on the new state from Firestore.
     * @param {object} state The playback state data.
     */
    function updateUI(state) {
        // Update Now Playing section
        if (state.current_track && state.is_playing) {
            const trackTitle = state.current_track.title || 'Unknown Title';
            const trackUrl = state.current_track.url || '#';
            const pausedText = state.is_paused ? ' (Paused)' : '';
            currentTrackEl.innerHTML = `<a href="${trackUrl}" target="_blank">${trackTitle}</a>${pausedText}`;
        } else {
            currentTrackEl.textContent = 'Nothing is playing.';
        }

        // Update Queue section
        queueListEl.innerHTML = ''; // Clear the list first
        if (state.queue && state.queue.length > 0) {
            state.queue.forEach(song => {
                const li = document.createElement('li');
                const songTitle = song.title || 'Unknown Title';
                li.textContent = songTitle;
                queueListEl.appendChild(li);
            });
        } else {
            const li = document.createElement('li');
            li.textContent = 'The queue is empty.';
            queueListEl.appendChild(li);
        }
    }
});
