# -*- coding: utf-8 -*-
import os
import jwt
import json
import datetime
from datetime import timezone
from functools import wraps
from urllib.parse import parse_qs, unquote_plus # Add unquote_plus
from flask import Flask, render_template, request, redirect, url_for, make_response, jsonify
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore

# Load environment variables from .env.local
load_dotenv(dotenv_path='.env.local')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SESSION_SECRET')

# --- Firebase Initialization ---
try:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialized successfully.")
except Exception as e:
    db = None
    print(f"Error initializing Firebase Admin SDK: {e}")

# --- Authentication Decorators ---
def page_token_required(f):
    """認証が必要なWebページ用のデコレータ。認証失敗時はログインページにリダイレクトする。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('auth_token')
        if not token:
            return redirect(url_for('login'))
        try:
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def api_token_required(f):
    """認証が必要なAPIエンドポイント用のデコレータ。認証失敗時はJSONエラーを返す。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('auth_token')
        if not token:
            return jsonify({'error': 'Authentication token is missing'}), 401
        try:
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return jsonify({'error': 'Invalid or expired authentication token'}), 401
        return f(*args, **kwargs)
    return decorated

# --- Routes ---

@app.route('/')
@page_token_required
def home():
    return render_template('search.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == os.getenv('APP_PASSWORD'):
            token = jwt.encode({
                'user': 'admin',
                'exp': datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=2)
            }, app.config['SECRET_KEY'], algorithm='HS256')
            response = make_response(redirect(url_for('home')))
            response.set_cookie('auth_token', token, httponly=True, max_age=7200, samesite='Lax')
            return response
        else:
            error = 'パスワードが違います'
            return render_template('login.html', error=error)
    return render_template('login.html')

@app.route('/api/search')
@api_token_required
def search():
    # Use Flask's standard request.args to get URL parameters.
    # This handles decoding and parsing automatically and correctly.
    query = request.args.get('q', '')
    
    print(f"DEBUG: Search API called. Query parameter 'q' received: '{query}' (type: {type(query)})")
    if not db or len(query) < 2:
        print(f"DEBUG: Returning empty due to no DB or short query: '{query}'")
        return jsonify([])
    try:
        collection_path = 'artifacts/default-app-id/public/data/horses'
        horses_ref = db.collection(collection_path)
        snapshot = horses_ref.where('name', '>=', query).where('name', '<=', query + '\uf8ff').limit(10).stream()
        results = [{'id': doc.id, 'name': doc.to_dict().get('name', 'N/A')} for doc in snapshot]
        return jsonify(results)
    except Exception as e:
        print(f"Search API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/artifact/<string:artifact_id>')
@page_token_required
def artifact_detail(artifact_id):
    def get_ancestor_tendency(ancestor_id):
        """指定されたIDの祖先の傾向データを取得する"""
        if not ancestor_id or ancestor_id == 'N/A':
            return {}
        try:
            tendency = {
                'by_course': [],
                'by_distance': []
            }
            # コース別成績を取得
            course_docs = db.collection(f'ancestors/{ancestor_id}/by_course').stream()
            tendency['by_course'] = [doc.to_dict() for doc in course_docs]
            
            # 距離別成績を取得
            distance_docs = db.collection(f'ancestors/{ancestor_id}/by_distance').stream()
            tendency['by_distance'] = [doc.to_dict() for doc in distance_docs]
            
            return tendency
        except Exception as e:
            logging.error(f"Error getting tendency data for {ancestor_id}: {e}")
            return {}

    def json_serial(obj):
        """DatetimeオブジェクトをJSONシリアライズ可能な形式に変換する"""
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    print(f"DEBUG: artifact_detail route called for ID: {artifact_id}")
    if not db:
        return "Firestore is not available.", 500
    try:
        collection_path = 'artifacts/default-app-id/public/data/horses'
        doc_ref = db.collection(collection_path).document(artifact_id)
        doc = doc_ref.get()

        if not doc.exists:
            return "Artifact not found", 404

        horse_data = doc.to_dict()
        
        # ▼▼▼ デバッグコードを追加 ▼▼▼
        print("\n--- DEBUG: Data from Firestore ---")
        print(horse_data)
        print("--- END DEBUG ---\n")
        # ▲▲▲ デバッグコードここまで ▲▲▲
        
        # 父と母の産駒成績データを取得
        sire_tendency = get_ancestor_tendency(horse_data.get('sire_id'))
        dam_tendency = get_ancestor_tendency(horse_data.get('dam_id'))

        # JSON表示用に、日付型を文字列に変換
        horse_data_json = json.dumps(horse_data, indent=2, ensure_ascii=False, default=json_serial)

        return render_template(
            'detail.html', 
            horse_id=artifact_id, 
            horse_data=horse_data, 
            horse_data_json=horse_data_json,
            sire_tendency=sire_tendency,
            dam_tendency=dam_tendency
        )
    except Exception as e:
        print(f"ERROR: Exception in artifact_detail for ID {artifact_id}: {e}")
        return "An error occurred.", 500

@app.route('/api/save_memo', methods=['POST'])
@api_token_required
def save_memo():
    if not db:
        return jsonify({'error': 'Firestore is not available.'}), 500
    
    data = request.get_json()
    if not data or 'horse_id' not in data or 'memo_text' not in data:
        return jsonify({'error': 'Invalid request. horse_id and memo_text are required.'}), 400

    horse_id = data['horse_id']
    memo_text = data['memo_text']

    try:
        collection_path = 'artifacts/default-app-id/public/data/horses'
        doc_ref = db.collection(collection_path).document(horse_id)
        
        if memo_text.strip() == '': # メモが空の場合
            doc_ref.update({'memo': firestore.DELETE_FIELD}) # フィールドを削除
        else: # メモがある場合
            doc_ref.update({'memo': memo_text}) # フィールドを更新
        
        logging.info(f"Memo for horse {horse_id} updated successfully.")
        return jsonify({'message': 'メモを保存しました！'}), 200
    except Exception as e:
        logging.error(f"Error saving memo for horse {horse_id}: {e}")
        return jsonify({'error': 'データベースへの保存中にエラーが発生しました。'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
