#!/usr/bin/env python3
"""
สคริปต์สำหรับเริ่มทั้ง Discord Bot และ Web Dashboard พร้อมกัน
"""
import os
import sys
import subprocess
import threading
import time
import signal
from pathlib import Path

# กำหนดพาธของไฟล์
BASE_DIR = Path(__file__).parent
BOT_FILE = BASE_DIR / "bot.py"
WEBAPP_FILE = BASE_DIR / "webapp.py"

class ProcessManager:
    def __init__(self):
        self.bot_process = None
        self.webapp_process = None
        self.running = True
        
    def start_bot(self):
        """เริ่ม Discord Bot"""
        try:
            print("[BOT] Starting Discord Bot...")
            self.bot_process = subprocess.Popen(
                [sys.executable, str(BOT_FILE)],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )
            
            # อ่าน output ของ bot
            for line in iter(self.bot_process.stdout.readline, ''):
                if not self.running:
                    break
                try:
                    print(f"[BOT] {line.strip()}")
                except UnicodeEncodeError:
                    print(f"[BOT] {line.strip().encode('ascii', 'replace').decode('ascii')}")
                
        except Exception as e:
            print(f"[ERROR] Error starting bot: {e}")
            
    def start_webapp(self):
        """เริ่ม Web Dashboard"""
        try:
            print("[WEB] Starting Web Dashboard...")
            # รอให้ bot เริ่มก่อน
            time.sleep(3)
            
            self.webapp_process = subprocess.Popen(
                [sys.executable, str(WEBAPP_FILE)],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )
            
            # อ่าน output ของ webapp
            for line in iter(self.webapp_process.stdout.readline, ''):
                if not self.running:
                    break
                try:
                    print(f"[WEB] {line.strip()}")
                except UnicodeEncodeError:
                    print(f"[WEB] {line.strip().encode('ascii', 'replace').decode('ascii')}")
                
        except Exception as e:
            print(f"[ERROR] Error starting webapp: {e}")
            
    def stop_all(self):
        """หยุดทุกกระบวนการ"""
        self.running = False
        print("\n[STOP] Stopping all processes...")
        
        if self.bot_process:
            try:
                self.bot_process.terminate()
                self.bot_process.wait(timeout=5)
                print("[SUCCESS] Bot stopped")
            except subprocess.TimeoutExpired:
                self.bot_process.kill()
                print("[WARNING] Bot force killed")
            except Exception as e:
                print(f"[ERROR] Error stopping bot: {e}")
                
        if self.webapp_process:
            try:
                self.webapp_process.terminate() 
                self.webapp_process.wait(timeout=5)
                print("[SUCCESS] Web dashboard stopped")
            except subprocess.TimeoutExpired:
                self.webapp_process.kill()
                print("[WARNING] Web dashboard force killed")
            except Exception as e:
                print(f"[ERROR] Error stopping webapp: {e}")

def signal_handler(signum, frame):
    """จัดการสัญญาณหยุดโปรแกรม"""
    print(f"\n[SIGNAL] Received signal {signum}")
    manager.stop_all()
    sys.exit(0)

def main():
    global manager
    
    print("Discord Bot Dashboard Launcher")
    print("=" * 50)
    
    # ตรวจสอบไฟล์ที่จำเป็น
    if not BOT_FILE.exists():
        print(f"[ERROR] Bot file not found: {BOT_FILE}")
        return 1
        
    if not WEBAPP_FILE.exists():
        print(f"[ERROR] Webapp file not found: {WEBAPP_FILE}")
        return 1
    
    # ตรวจสอบไฟล์ .env
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        print(f"[WARNING] .env file not found at {env_file}")
        print("Make sure environment variables are set!")
    
    manager = ProcessManager()
    
    # ตั้งค่า signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # สร้าง threads สำหรับแต่ละกระบวนการ
        bot_thread = threading.Thread(target=manager.start_bot, daemon=True)
        webapp_thread = threading.Thread(target=manager.start_webapp, daemon=True)
        
        # เริ่ม threads
        bot_thread.start()
        webapp_thread.start()
        
        print("\n[SUCCESS] Both services are starting...")
        print("[INFO] Web Dashboard: http://localhost:5001")
        print("[INFO] Bot: Check console logs above")
        print("\n[TIP] Press Ctrl+C to stop all services")
        
        # รอให้ threads ทำงานเสร็จ
        bot_thread.join()
        webapp_thread.join()
        
    except KeyboardInterrupt:
        print("\n[CTRL+C] Keyboard interrupt received")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        manager.stop_all()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())