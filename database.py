import os
import threading
import json
import firebase_admin
from firebase_admin import credentials, firestore

# 全域變數，用於儲存 Firestore 客戶端實例和 Thread-Local 儲存
db = None
thread_local = threading.local()

def initialize_database():
    """初始化 Firebase 服務與 Firestore 客戶端"""
    global db
    if firebase_admin._apps:
        print("Firebase 已初始化，無需重複初始化。")
        return

    # 檢查是否有服務帳號金鑰檔案路徑的環境變數
    cred_file_path = os.getenv("FIREBASE_CREDENTIALS_FILE")
    cred_obj = None

    if cred_file_path and os.path.exists(cred_file_path):
        print("偵測到 FIREBASE_CREDENTIALS_FILE，嘗試從檔案讀取憑證...")
        try:
            with open(cred_file_path, 'r') as f:
                cred_obj = json.load(f)
            cred = credentials.Certificate(cred_obj)
            firebase_admin.initialize_app(cred)
            print("Firebase 已成功初始化 (模式: 服務帳號金鑰檔案)")
        except Exception as e:
            print(f"Firebase 初始化失敗: 無法從檔案讀取憑證。錯誤訊息: {e}")
            raise e
    else:
        # 如果沒有檔案路徑，退回原先的環境變數字串模式
        print("🟡 未偵測到 FIREBASE_CREDENTIALS_FILE，嘗試從 FIREBASE_ADMIN_CREDENTIALS 讀取憑證。")
        cred_json = os.getenv("FIREBASE_ADMIN_CREDENTIALS")
        if cred_json:
            print("偵測到 FIREBASE_ADMIN_CREDENTIALS 環境變數，嘗試從字串讀取...")
            try:
                cred_obj = json.loads(cred_json)
                cred = credentials.Certificate(cred_obj)
                firebase_admin.initialize_app(cred)
                print("Firebase 已成功初始化 (模式: 環境變數字串)")
            except Exception as e:
                print(f"Firebase 初始化失敗: 無法從字串讀取憑證。錯誤訊息: {e}")
                raise e
        else:
            # 如果都找不到，嘗試使用 Application Default
            print("🟡 未找到 FIREBASE_ADMIN_CREDENTIALS，嘗試使用 ApplicationDefault。")
            try:
                firebase_admin.initialize_app()
                print("Firebase 已成功初始化 (模式: 應用預設憑證)")
            except Exception as e:
                print(f"Firebase 初始化失敗: {e}")
                print("請檢查你的本地環境是否已設定 ADC，或提供一個有效的服務帳號金鑰。")
                raise e # 為了確保 main 函式能捕捉到錯誤並停止，這裡重新拋出異常

    db = firestore.client()
    print("✅ Firestore 客戶端已成功初始化。")
    print("-" * 30)

def get_db():
    """獲取 Firestore 客戶端實例"""
    if not firebase_admin._apps:
        initialize_database()
    return db

# 使用 Thread-Local 來管理 Firestore 客戶端，避免多執行緒問題
def get_thread_local_db():
    if not hasattr(thread_local, 'db'):
        thread_local.db = get_db()
    return thread_local.db

def get_user_profile(user_id):
    """從 Firestore 獲取用戶資料"""
    db = get_thread_local_db()
    try:
        doc_ref = db.collection('user_profiles').document(str(user_id))
        doc = doc_ref.get()
        if doc.exists:
            profile = doc.to_dict()
            # 確保舊資料也能相容新欄位
            if 'recent_history' not in profile:
                profile['recent_history'] = []
            return profile
        else:
            print(f"⚠️ 用戶 {user_id} 的資料不存在，建立預設檔案。")
            default_profile = {
                'discord_id': user_id,
                'name': '',
                'current_role': '',
                'keywords': [],
                'recent_history': [] # 新增：儲存最近 4 句對話
            }
            doc_ref.set(default_profile)
            return default_profile
    except Exception as e:
        print(f"獲取用戶資料失敗: {e}")
        return None

def add_to_history(user_id, role, content):
    """
    紀錄最近對話 4句
    role: 'bot' (自己) 或 'user' (對方)
    """
    db = get_thread_local_db()
    try:
        doc_ref = db.collection('user_profiles').document(str(user_id))
        doc = doc_ref.get()
        if doc.exists:
            profile = doc.to_dict()
            history = profile.get('recent_history', [])
            
            history.append({"r": role, "m": content, "t": __import__('time').time()})

            if len(history) > 4:
                history = history[-4:]
            
            doc_ref.update({'recent_history': history})
    except Exception as e:
        print(f"紀錄對話歷史失敗: {e}")

def update_user_profile(user_id, data):
    """更新用戶在 Firestore 中的資料"""
    db = get_thread_local_db()
    try:
        doc_ref = db.collection('user_profiles').document(str(user_id))
        doc_ref.set(data, merge=True)
        print(f"成功更新用戶 {user_id} 的資料。")
    except Exception as e:
        print(f" 更新用戶資料失敗: {e}")
        
# === bot Mount time ===
def add_uptime_hours(hours=1):
    db = get_thread_local_db()
    try:
        doc_ref = db.collection('bot_stats').document('uptime')
        doc = doc_ref.get()
        current = doc.to_dict().get('total_hours', 0) if doc.exists else 0
        doc_ref.set({'total_hours': current + hours}, merge=True)
    except Exception as e:
        print(f"更新運行時間失敗: {e}")

def get_total_uptime():
    db = get_thread_local_db()
    try:
        doc = db.collection('bot_stats').document('uptime').get()
        return doc.to_dict().get('total_hours', 0) if doc.exists else 0
    except Exception as e:
        print(f"讀取運行時間失敗: {e}")
        return 0

def set_start_date(date_str):
    db = get_thread_local_db()
    try:
        doc_ref = db.collection('bot_stats').document('uptime')
        doc = doc_ref.get()
        if not doc.exists or 'start_date' not in doc.to_dict():
            doc_ref.set({'start_date': date_str}, merge=True)
    except Exception as e:
        print(f"寫入啟動日期失敗: {e}")
# === bot Mount time ===