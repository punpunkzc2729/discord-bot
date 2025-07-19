# webapp/app.py
import os
from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from flask_discord import DiscordOAuth2Session, requires_authorization, Unauthorized
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
import logging

# --- Initialization ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# --- Flask Configuration ---
# It's crucial that these environment variables are set correctly.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "a_default_secret_key_for_development")
# In production, this MUST be set to "false" or not set at all.
# It allows OAuth2 to work over HTTP for local development.
if os.getenv("FLASK_ENV") == "development":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"

app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
app.config["DISCORD_BOT_TOKEN"] = os.getenv("DISCORD_TOKEN") # Required to fetch bot's guilds

# --- Firebase Initialization ---
try:
    FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logging.info("Firebase initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize Firebase: {e}")
    db = None

# --- Discord OAuth2 Setup ---
discord = DiscordOAuth2Session(app)

def is_authorized():
    """Checks if the logged-in user is in the authorized_staff collection in Firestore."""
    if not db or not discord.authorized:
        return False
    try:
        user = discord.fetch_user()
        staff_ref = db.collection('authorized_staff').document(str(user.id))
        return staff_ref.get().exists
    except Exception as e:
        logging.error(f"Error checking authorization for user: {e}")
        return False

# --- Web Routes ---
@app.route("/")
def index():
    """
    Renders the main page. If the user is logged in and authorized, it shows the dashboard.
    Otherwise, it shows the login page.
    """
    if discord.authorized and is_authorized():
        user = discord.fetch_user()
        
        # Fetch guilds the user is in and guilds the bot is in
        user_guilds = discord.fetch_guilds()
        bot_guilds_data = discord.bot_request('/users/@me/guilds')
        bot_guild_ids = {g['id'] for g in bot_guilds_data}

        # Find the guilds they have in common
        shared_guilds = [g for g in user_guilds if str(g.id) in bot_guild_ids]
        
        return render_template("dashboard.html", user=user, guilds=shared_guilds)
    return render_template("login.html")

@app.route("/login/")
def login():
    """Redirects user to Discord's OAuth2 authorization page."""
    # We need 'identify' for user info and 'guilds' to see which servers they're in.
    return discord.create_session(scope=['identify', 'guilds'])

@app.route("/callback/")
def callback():
    """Handles the OAuth2 callback from Discord after the user authorizes."""
    try:
        discord.callback()
        user = discord.fetch_user()
        session['user_id'] = user.id # Store user ID in session
    except Exception as e:
        logging.error(f"OAuth callback error: {e}")
        return redirect(url_for("login"))
    return redirect(url_for("index"))

@app.route("/logout/")
def logout():
    """Logs the user out by revoking the session and clearing local session data."""
    discord.revoke()
    session.clear()
    return redirect(url_for("index"))

@app.route("/logs")
@requires_authorization
def logs():
    """(P2) Displays error logs for authorized admins."""
    if not is_authorized():
        return redirect(url_for('index'))
    
    error_logs = []
    if db:
        logs_ref = db.collection('error_logs').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(50)
        error_logs = [doc.to_dict() for doc in logs_ref.stream()]
    
    return render_template('logs.html', logs=error_logs)


# --- API Routes (for frontend JS) ---
@app.route("/api/command", methods=["POST"])
@requires_authorization
def command():
    """
    Receives a command from the web dashboard's frontend, validates it,
    and pushes it to the corresponding guild's command queue in Firestore.
    """
    if not is_authorized():
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    if not db:
        return jsonify({"status": "error", "message": "Database not configured"}), 500

    data = request.json
    guild_id = data.get("guild_id")
    action = data.get("action")
    payload = data.get("payload")
    user = discord.fetch_user()

    if not all([guild_id, action]):
        return jsonify({"status": "error", "message": "Missing required data (guild_id, action)"}), 400

    try:
        # Push command to Firestore for the bot to pick up
        command_ref = db.collection('guilds').document(guild_id).collection('commands')
        command_ref.add({
            'action': action,
            'payload': payload,
            'requester_id': str(user.id),
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        return jsonify({"status": "success", "message": "Command sent"})
    except Exception as e:
        logging.error(f"Error pushing command to Firestore: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.errorhandler(Unauthorized)
def redirect_unauthorized(e):
    """Handles unauthorized access by redirecting to the login page."""
    return redirect(url_for("login"))

if __name__ == "__main__":
    # Set FLASK_ENV=development in your .env file for development
    is_development = os.getenv("FLASK_ENV") == "development"
    app.run(debug=is_development, port=5001)
