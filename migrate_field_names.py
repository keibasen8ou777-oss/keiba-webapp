import firebase_admin
from firebase_admin import credentials, firestore
import os

def migrate_data():
    """
    Firestoreの'horses'コレクションのフィールド名を日本語から英語に移行する
    """
    print("Starting data migration...")
    
    try:
        # --- Firebase Initialization ---
        # スクリプトのあるディレクトリを基準にサービスアカウントキーを探す
        script_dir = os.path.dirname(__file__)
        key_path = os.path.join(script_dir, 'serviceAccountKey.json')
        
        cred = credentials.Certificate(key_path)
        
        # すでに初期化されている場合はエラーになるため、既存のインスタンスを取得する
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        print("Firebase Admin SDK initialized successfully.")

    except Exception as e:
        print(f"Error initializing Firebase Admin SDK: {e}")
        print("Please make sure 'serviceAccountKey.json' is in the same directory as this script.")
        return

    # --- Field Name Mapping ---
    FIELD_MAPPING = {
        '馬名': 'name',
        '父': 'sire',
        '母': 'dam',
        '父父': 'paternal_grandsire',
        '父母': 'paternal_granddam',
        '母父': 'maternal_grandsire',
        '母母': 'maternal_granddam'
    }

    collection_ref = db.collection('artifacts/default-app-id/public/data/horses')
    
    try:
        docs = list(collection_ref.stream())
    except Exception as e:
        print(f"Failed to retrieve documents from Firestore: {e}")
        return
    
    if not docs:
        print("No documents found in the collection. Nothing to migrate.")
        return

    updated_count = 0
    
    # バッチ処理を使用して、複数のドキュメントを一度に効率的に更新する
    batch = db.batch()
    
    print(f"Found {len(docs)} documents to process...")

    for doc in docs:
        doc_data = doc.to_dict()
        update_payload = {}
        needs_update = False
        
        for jp_field, en_field in FIELD_MAPPING.items():
            if jp_field in doc_data:
                update_payload[en_field] = doc_data[jp_field]
                update_payload[jp_field] = firestore.DELETE_FIELD
                needs_update = True

        if needs_update:
            batch.update(doc.reference, update_payload)
            updated_count += 1
            
            # Firestoreのバッチは500操作までという制限があるため、余裕を持って400で一度コミット
            if (updated_count % 400 == 0):
                print(f"Committing batch of 400 updates... (Total processed: {updated_count})")
                batch.commit()
                batch = db.batch() # 新しいバッチを開始

    # 残りのバッチをコミット
    if (updated_count % 400) > 0:
        print(f"Committing final batch of {updated_count % 400} updates...")
        batch.commit()

    print("\nMigration finished.")
    print(f"Total documents updated: {updated_count}")

if __name__ == '__main__':
    migrate_data()
