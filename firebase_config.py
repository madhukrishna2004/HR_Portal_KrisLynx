"""
KrisLynx LLP – HR Portal  |  firebase_config.py

Supports two initialization modes:
  1. LOCAL  – reads serviceAccountKey.json from disk (dev convenience)
  2. RENDER – reads FIREBASE_SERVICE_ACCOUNT_JSON env var (production)
"""

import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage
from dotenv import load_dotenv

load_dotenv()

COLLECTIONS = {
    "users":         "krislynxllp_hr_users",
    "projects":      "krislynxllp_hr_projects",
    "tasks":         "krislynxllp_hr_tasks",
    "eod_reports":   "krislynxllp_hr_eod_reports",
    "activity_logs": "krislynxllp_hr_activity_logs",
}

STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "miyraa-59c25.appspot.com")

CLIENT_CONFIG = {
    "apiKey":            os.getenv("FIREBASE_API_KEY",            ""),
    "authDomain":        os.getenv("FIREBASE_AUTH_DOMAIN",        "miyraa-59c25.firebaseapp.com"),
    "projectId":         os.getenv("FIREBASE_PROJECT_ID",         "miyraa-59c25"),
    "storageBucket":     STORAGE_BUCKET,
    "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID",""),
    "appId":             os.getenv("FIREBASE_APP_ID",             ""),
}


def init_firebase():
    if firebase_admin._apps:
        return

    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        try:
            sa_dict = json.loads(sa_json)
            cred    = credentials.Certificate(sa_dict)
            firebase_admin.initialize_app(cred, {"storageBucket": STORAGE_BUCKET})
            print("Firebase initialized from environment variable")
            return
        except Exception as e:
            print(f"Firebase env var init error: {e}")
            raise

    key_file = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")
    if os.path.exists(key_file):
        try:
            cred = credentials.Certificate(key_file)
            firebase_admin.initialize_app(cred, {"storageBucket": STORAGE_BUCKET})
            print("Firebase initialized from serviceAccountKey.json")
            return
        except Exception as e:
            print(f"Firebase file init error: {e}")
            raise

    raise RuntimeError(
        "Firebase credentials not found.\n"
        "Set FIREBASE_SERVICE_ACCOUNT_JSON env var on Render,\n"
        "or place serviceAccountKey.json in project root locally."
    )


def get_db():
    init_firebase()
    return firestore.client()

def get_auth():
    init_firebase()
    return auth

def get_bucket():
    init_firebase()
    return storage.bucket()
