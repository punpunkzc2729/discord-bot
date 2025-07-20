# webapp.py
import os
import sys
import re
from flask import Flask, render_template, redirect, url_for, session, request, jsonify
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
import logging
import requests
from functools import wraps
from typing import Optional, Dict, List
import bleach
from urllib.parse import urlparse

# --- การตั้งค่าเริ่มต้น ---
load_dotenv()

# Configure console output encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Setup detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('webapp.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Security headers middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'"
    return response

# Input validation functions
def validate_guild_id(guild_id: str) -> bool:
    """Validate Discord guild ID format"""
    return bool(re.match(r'^\d{17,19}$', guild_id))

def validate_action(action: str) -> bool:
    """Validate allowed actions"""
    allowed_actions = ['play', 'skip', 'stop', 'pause', 'resume', 'queue']
    return action in allowed_actions

def sanitize_query(query: str) -> str:
    """Sanitize search query input"""
    if not query:
        return ""
    
    # Remove any potential harmful content
    sanitized = bleach.clean(query.strip(), tags=[], strip=True)
    
    # Limit length
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    
    return sanitized

# Validate required environment variables
required_env_vars = {
    "FLASK_SECRET_KEY": "Flask secret key for sessions",
    "DISCORD_CLIENT_ID": "Discord application client ID", 
    "DISCORD_CLIENT_SECRET": "Discord application client secret",
    "DISCORD_REDIRECT_URI": "Discord OAuth redirect URI",
    "DISCORD_TOKEN": "Discord bot token",
    "FIREBASE_CREDENTIALS_PATH": "Path to Firebase credentials JSON"
}

missing_vars = []
for var, description in required_env_vars.items():
    if not os.getenv(var):
        missing_vars.append(f"{var} ({description})")

if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    print(f"❌ Missing environment variables:\n" + "\n".join(f"  - {var}" for var in missing_vars))
    exit(1)

app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
app.config["DISCORD_BOT_TOKEN"] = os.getenv("DISCORD_TOKEN")

# อนุญาต OAuth ผ่าน HTTP สำหรับการทดสอบบนเครื่อง
if os.getenv("FLASK_ENV") == "development":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "true"
    logger.info("Development mode: allowing insecure OAuth transport")

# --- การเชื่อมต่อ Firebase ---
try:
    FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if not os.path.exists(FIREBASE_CREDENTIALS_PATH):
        raise FileNotFoundError(f"Firebase credentials file not found: {FIREBASE_CREDENTIALS_PATH}")
    
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    # Use a different app name to avoid conflicts with bot.py
    try:
        firebase_admin.initialize_app(cred, name='webapp')
    except ValueError:
        # App already exists, get existing app
        pass
    
    firebase_app = firebase_admin.get_app('webapp')
    db = firestore.client(app=firebase_app)
    logger.info("Firebase connection established successfully")
except Exception as e:
    logger.error(f"Failed to connect to Firebase: {e}")
    print(f"❌ Firebase connection failed: {e}")
    db = None

# --- Discord OAuth2 Implementation ---
DISCORD_API_ENDPOINT = "https://discord.com/api/v10"

def requires_discord_auth(f):
    """Decorator to require Discord authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'discord_token' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_discord_user(access_token: str) -> Optional[Dict]:
    """Get Discord user info from access token"""
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to get Discord user: {e}")
        return None

def get_discord_guilds(access_token: str) -> List[Dict]:
    """Get Discord user's guilds"""
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to get Discord guilds: {e}")
        return []

def get_bot_guilds() -> List[Dict]:
    """Get bot's guilds"""
    try:
        headers = {"Authorization": f"Bot {app.config['DISCORD_BOT_TOKEN']}"}
        response = requests.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to get bot guilds: {e}")
        return []

def is_authorized() -> bool:
    """ตรวจสอบว่าผู้ใช้ที่ล็อกอินได้รับอนุญาตหรือไม่"""
    # สำหรับตอนนี้ เราจะอนุญาตทุกคนที่ล็อกอินได้
    # หากต้องการจำกัดสิทธิ์ ให้สร้าง collection 'authorized_staff' ใน Firestore
    return 'discord_token' in session and session.get('discord_user') is not None

# --- Web Routes ---
@app.route("/")
def index():
    """หน้าหลัก: แสดง Dashboard ถ้าล็อกอินแล้ว, หรือหน้า Login ถ้ายัง"""
    try:
        if not is_authorized():
            return render_template("login.html")
        
        access_token = session.get('discord_token')
        user = session.get('discord_user')
        
        if not user:
            # ดึงข้อมูล user ใหม่หากไม่มีใน session
            user = get_discord_user(access_token)
            if not user:
                return redirect(url_for('logout'))
            session['discord_user'] = user
        
        # ดึงข้อมูล guilds
        user_guilds = get_discord_guilds(access_token)
        bot_guilds = get_bot_guilds()
        
        # หา guilds ที่ทั้ง user และ bot อยู่ด้วยกัน
        bot_guild_ids = {g['id'] for g in bot_guilds}
        shared_guilds = [g for g in user_guilds if g['id'] in bot_guild_ids]
        
        # สร้าง avatar URL
        if user.get('avatar'):
            user['avatar_url'] = f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png"
        else:
            user['avatar_url'] = f"https://cdn.discordapp.com/embed/avatars/{int(user['discriminator']) % 5}.png"
        
        logger.info(f"User {user['username']} accessed dashboard with {len(shared_guilds)} shared guilds")
        return render_template("dashboard.html", user=user, guilds=shared_guilds)
        
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        return redirect(url_for('logout'))

@app.route("/login")
def login():
    """ส่งผู้ใช้ไปหน้า Authorize ของ Discord พร้อม CSRF protection"""
    try:
        import secrets
        
        # สร้าง state parameter สำหรับ CSRF protection
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        
        # สร้าง Discord OAuth URL พร้อม state parameter
        oauth_url = (
            f"https://discord.com/api/oauth2/authorize"
            f"?client_id={app.config['DISCORD_CLIENT_ID']}"
            f"&redirect_uri={app.config['DISCORD_REDIRECT_URI']}"
            f"&response_type=code"
            f"&scope=identify%20guilds"
            f"&state={state}"
        )
        return redirect(oauth_url)
    except Exception as e:
        logger.error(f"Error in login route: {e}")
        return render_template("login.html", error="เกิดข้อผิดพลาดในการเข้าสู่ระบบ")

@app.route("/callback")
def callback():
    """รับข้อมูลกลับมาจาก Discord หลังล็อกอิน พร้อม state validation"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')
        
        # ตรวจสอบ state parameter เพื่อป้องกัน CSRF
        if not state or state != session.get('oauth_state'):
            logger.warning("Invalid or missing OAuth state parameter")
            return redirect(url_for('login'))
        
        # ลบ state จาก session หลังใช้แล้ว
        session.pop('oauth_state', None)
        
        if not code:
            logger.warning("No authorization code received")
            return redirect(url_for('login'))
        
        # แลก authorization code กับ access token
        token_data = {
            'client_id': app.config['DISCORD_CLIENT_ID'],
            'client_secret': app.config['DISCORD_CLIENT_SECRET'],
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': app.config['DISCORD_REDIRECT_URI']
        }
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        token_response = requests.post(
            f"{DISCORD_API_ENDPOINT}/oauth2/token",
            data=token_data,
            headers=headers
        )
        token_response.raise_for_status()
        token_json = token_response.json()
        
        access_token = token_json.get('access_token')
        if not access_token:
            raise ValueError("No access token received")
        
        # ดึงข้อมูล user
        user = get_discord_user(access_token)
        if not user:
            raise ValueError("Failed to get user information")
        
        # เก็บข้อมูลใน session
        session['discord_token'] = access_token
        session['discord_user'] = user
        
        logger.info(f"User {user['username']} logged in successfully")
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return redirect(url_for('login'))

@app.route("/logout")
def logout():
    """ออกจากระบบ"""
    try:
        user = session.get('discord_user', {})
        username = user.get('username', 'Unknown')
        session.clear()
        logger.info(f"User {username} logged out")
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error in logout: {e}")
        session.clear()
        return redirect(url_for('index'))

# --- API Route สำหรับรับคำสั่งจากหน้าเว็บ ---
@app.route("/api/command", methods=["POST"])
@requires_discord_auth
def command():
    try:
        if not db:
            return jsonify({
                "status": "error", 
                "message": "Database not available"
            }), 503
            
        if not is_authorized():
            return jsonify({
                "status": "error", 
                "message": "ไม่ได้รับอนุญาต"
            }), 403

        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error", 
                "message": "Invalid JSON data"
            }), 400

        guild_id = data.get("guild_id")
        action = data.get("action")
        payload = data.get("payload", {})
        
        # Enhanced input validation
        if not guild_id or not action:
            return jsonify({
                "status": "error", 
                "message": "ข้อมูลไม่ครบถ้วน (guild_id และ action จำเป็น)"
            }), 400

        # Validate guild ID format
        if not validate_guild_id(str(guild_id)):
            return jsonify({
                "status": "error", 
                "message": "Guild ID format ไม่ถูกต้อง"
            }), 400

        # Validate action type
        if not validate_action(action):
            return jsonify({
                "status": "error", 
                "message": f"Action ไม่ถูกต้อง ต้องเป็น: play, skip, stop, pause, resume, queue"
            }), 400
        
        # Sanitize payload
        if isinstance(payload, dict):
            if 'query' in payload:
                payload['query'] = sanitize_query(payload['query'])
        else:
            payload = {}

        user = session.get('discord_user')
        if not user:
            return jsonify({
                "status": "error", 
                "message": "User session not found"
            }), 401

        # ส่งคำสั่งไปที่ Firestore เพื่อให้บอทรับไปทำงานต่อ
        command_data = {
            'action': action,
            'payload': payload,
            'requester_id': str(user['id']),
            'requester_username': user['username'],
            'timestamp': firestore.SERVER_TIMESTAMP,
            'status': 'pending'
        }
        
        command_ref = db.collection('guilds').document(guild_id).collection('commands')
        doc_ref = command_ref.add(command_data)
        
        logger.info(f"Command {action} sent to guild {guild_id} by user {user['username']}")
        
        return jsonify({
            "status": "success",
            "command_id": doc_ref[1].id,
            "message": f"ส่งคำสั่ง {action} เรียบร้อยแล้ว"
        })
        
    except Exception as e:
        logger.error(f"Error in command API: {e}")
        return jsonify({
            "status": "error", 
            "message": "เกิดข้อผิดพลาดภายในเซิร์ฟเวอร์"
        }), 500

# --- Error Handlers ---
@app.errorhandler(404)
def not_found(error):
    return render_template('login.html', error="หน้าที่ต้องการไม่พบ"), 404

@app.errorhandler(500) 
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return render_template('login.html', error="เกิดข้อผิดพลาดของเซิร์ฟเวอร์"), 500

# --- Main Execution ---
if __name__ == "__main__":
    try:
        logger.info("Starting Flask web application")
        print("[WEB] Starting Discord Bot Dashboard...")
        print("[WEB] Access at: http://localhost:5001")
        app.run(debug=True, port=5001, host='0.0.0.0')
    except Exception as e:
        logger.error(f"Failed to start web application: {e}")
        print(f"[ERROR] Failed to start web application: {e}")

