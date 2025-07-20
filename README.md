# Discord Bot Dashboard

🎵 A comprehensive Discord music bot with web dashboard for remote control and monitoring.

## Features

### Discord Bot Commands
- `/play` - Play music from YouTube
- `/skip` - Skip current track
- `/stop` - Stop playback and clear queue
- `/list` - Show current queue
- `/speak` - Text-to-speech in Thai
- `/wake` - Send DM to wake up friends
- `/leave` - Leave voice channel

### Web Dashboard
- Discord OAuth authentication
- Server selection
- Remote music control
- Real-time playback status
- Queue management
- Responsive design

## Setup Instructions

### 1. Prerequisites
- Python 3.8 or higher
- FFmpeg installed and in PATH
- Discord application with bot token
- Firebase project (optional, for real-time features)

### 2. Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd discord-bot-dashboard
```

2. Create and activate virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configuration

1. Copy environment template:
```bash
cp .env.example .env
```

2. Edit `.env` file with your configuration:
```env
DISCORD_TOKEN=your_bot_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=http://localhost:5001/callback
FLASK_SECRET_KEY=your_secret_key
FIREBASE_CREDENTIALS_PATH=path/to/firebase-credentials.json
```

### 4. Discord Application Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create new application
3. Go to "Bot" section and create bot
4. Copy bot token to `.env`
5. Go to "OAuth2" section:
   - Add redirect URI: `http://localhost:5001/callback`
   - Copy Client ID and Secret to `.env`

### 5. Running the Application

1. Start the Discord bot:
```bash
python bot.py
```

2. Start the web dashboard (in another terminal):
```bash
python webapp.py
```

3. Access dashboard at: http://localhost:5001

## Project Structure

```
discord-bot-dashboard/
├── bot.py                 # Discord bot main file
├── webapp.py             # Flask web application
├── requirements.txt      # Python dependencies
├── .env.example         # Environment variables template
├── static/
│   ├── style.css        # Web dashboard styles
│   └── main.js          # Frontend JavaScript
├── templates/
│   ├── dashboard.html   # Main dashboard template
│   └── login.html       # Login page template
└── application.yml      # Lavalink configuration (optional)
```

## Error Handling & Logging

The application includes comprehensive error handling:
- Detailed logging to console and files
- Graceful fallbacks when services are unavailable
- User-friendly error messages
- Automatic cleanup of temporary files

## Troubleshooting

### Common Issues

1. **FFmpeg not found**
   - Install FFmpeg and add to system PATH
   - Windows: Download from https://ffmpeg.org/
   - Linux: `sudo apt install ffmpeg`
   - Mac: `brew install ffmpeg`

2. **Bot can't join voice channel**
   - Check bot permissions in Discord server
   - Ensure bot has "Connect" and "Speak" permissions

3. **Web dashboard not loading**
   - Check if Flask is running on port 5001
   - Verify Discord OAuth settings
   - Check browser console for errors

4. **Firebase errors**
   - Verify credentials file path
   - Check Firebase project settings
   - App works without Firebase for basic functionality

### Logs

Check log files for detailed error information:
- `bot.log` - Discord bot logs
- `webapp.log` - Web application logs

## Development

### Adding New Commands

1. Add command function in `bot.py`:
```python
@bot.tree.command(name="mycommand", description="My new command")
async def my_command(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!")
```

2. Add web API endpoint in `webapp.py` if needed
3. Update frontend in `main.js` for web control

### Code Style

- Use proper error handling with try-catch blocks
- Add logging for important operations
- Follow existing code patterns
- Use type hints where possible

## License

This project is provided as-is for educational purposes.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review log files for error details
3. Ensure all dependencies are properly installed
4. Verify environment variables are set correctly