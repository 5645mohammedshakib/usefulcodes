"""
Student Hub - Python Flask Backend Server
Run: python server.py
API runs at: http://localhost:5000
"""

import os
import uuid
import datetime
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ─── Config ────────────────────────────────────────────────────────────────────
MONGO_URI   = os.getenv("MONGO_URI",   "mongodb://127.0.0.1:27017/student_hub")
JWT_SECRET  = os.getenv("JWT_SECRET",  "student_hub_admin_supersecretkey_2026!@#")
PORT        = int(os.getenv("PORT",    5000))
UPLOAD_DIR  = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ─── DB ────────────────────────────────────────────────────────────────────────
client = MongoClient(MONGO_URI)
db     = client.get_database()

users         = db["users"]
notes_col     = db["notes"]
assignments   = db["assignments"]
papers_col    = db["papers"]
announcements = db["announcements"]
timetables    = db["timetables"]
syllabi       = db["syllabi"]
categories    = db["categories"]

# ─── Health / Keep-Alive ───────────────────────────────────────────────────────
@app.route('/')
def root():
    return jsonify({"status": "ok", "app": "Student Hub API", "version": "1.0"})

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "message": "Server is alive!"})

# ─── Helpers ───────────────────────────────────────────────────────────────────
def serialize(doc):
    """Convert MongoDB document to JSON-serialisable dict."""
    if doc is None:
        return None
    doc = dict(doc)
    doc["_id"] = str(doc["_id"])
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        elif isinstance(v, datetime.datetime):
            doc[k] = v.isoformat()
    return doc

def make_token(user_id: str) -> str:
    payload = {
        "user": {"id": user_id},
        "exp":  datetime.datetime.utcnow() + datetime.timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def auth_required(f):
    """JWT auth decorator — sets request.user_id."""
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get("Authorization") or request.headers.get("x-auth-token")
        if not header:
            return jsonify({"msg": "No token, authorization denied"}), 401
        token = header.replace("Bearer ", "").strip()
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user_id = data["user"]["id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"msg": "Token expired"}), 401
        except Exception:
            return jsonify({"msg": "Token is not valid"}), 401
        return f(*args, **kwargs)
    return decorated

def save_file(file_obj) -> str | None:
    """Save uploaded file, return relative URL."""
    if not file_obj or not file_obj.filename:
        return None
    ext      = os.path.splitext(file_obj.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    file_obj.save(os.path.join(UPLOAD_DIR, filename))
    return f"/uploads/{filename}"

# ─── Static uploads ────────────────────────────────────────────────────────────
@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ─── Root ──────────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return jsonify({"msg": "Student Hub Python Backend Running ✅"})

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH  /api/auth
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/auth/register")
def register():
    data     = request.get_json(force=True)
    name     = data.get("name", "").strip()
    email    = data.get("email", "").strip().lower()
    username = data.get("username", email).strip()   # support plain username too
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"errors": [{"msg": "Email and password required"}]}), 400

    if users.find_one({"$or": [{"email": email}, {"username": username}]}):
        return jsonify({"errors": [{"msg": "User already exists"}]}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    uid    = users.insert_one({
        "name":      name or username,
        "email":     email,
        "username":  username,
        "password":  hashed,
        "role":      "user",
        "createdAt": datetime.datetime.utcnow(),
    }).inserted_id

    return jsonify({"token": make_token(str(uid))})

@app.post("/api/auth/login")
def login():
    data     = request.get_json(force=True)
    # Accept either email or username in the "email" field
    email_or_username = (data.get("email") or data.get("username") or "").strip().lower()
    password = data.get("password", "")

    user = users.find_one({
        "$or": [
            {"email":    email_or_username},
            {"username": email_or_username},
        ]
    })
    if not user:
        return jsonify({"errors": [{"msg": "Invalid credentials"}]}), 400

    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"errors": [{"msg": "Invalid credentials"}]}), 400

    return jsonify({"token": make_token(str(user["_id"]))})

@app.get("/api/auth/me")
@auth_required
def get_me():
    user = users.find_one({"_id": ObjectId(request.user_id)}, {"password": 0})
    if not user:
        return jsonify({"msg": "User not found"}), 404
    return jsonify(serialize(user))

# ══════════════════════════════════════════════════════════════════════════════
#  USERS  /api/users
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/users")
@auth_required
def get_users():
    all_users = [serialize(u) for u in users.find({}, {"password": 0})]
    return jsonify(all_users)

@app.delete("/api/users/<user_id>")
@auth_required
def delete_user(user_id):
    requester = users.find_one({"_id": ObjectId(request.user_id)})
    if not requester or requester.get("role") != "admin":
        return jsonify({"msg": "Admin privileges required"}), 403
    users.delete_one({"_id": ObjectId(user_id)})
    return jsonify({"msg": "User deleted"})

# ══════════════════════════════════════════════════════════════════════════════
#  NOTES  /api/notes
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/notes")
def get_notes():
    return jsonify([serialize(n) for n in notes_col.find().sort("createdAt", -1)])

@app.post("/api/notes")
@auth_required
def create_note():
    title       = request.form.get("title", "")
    description = request.form.get("description", "")
    category    = request.form.get("category", "")
    file_url    = save_file(request.files.get("file"))
    doc = {
        "title":       title,
        "description": description,
        "category":    category,
        "fileUrl":     file_url,
        "createdBy":   request.user_id,
        "createdAt":   datetime.datetime.utcnow(),
    }
    ins = notes_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    return jsonify(doc), 201

@app.delete("/api/notes/<note_id>")
@auth_required
def delete_note(note_id):
    notes_col.delete_one({"_id": ObjectId(note_id)})
    return jsonify({"msg": "Note deleted"})

@app.put("/api/notes/<note_id>")
@auth_required
def update_note(note_id):
    data = request.get_json(force=True)
    notes_col.update_one({"_id": ObjectId(note_id)}, {"$set": data})
    note = notes_col.find_one({"_id": ObjectId(note_id)})
    return jsonify(serialize(note))

# ══════════════════════════════════════════════════════════════════════════════
#  ASSIGNMENTS  /api/assignments
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/assignments")
def get_assignments():
    return jsonify([serialize(a) for a in assignments.find().sort("createdAt", -1)])

@app.post("/api/assignments")
@auth_required
def create_assignment():
    title       = request.form.get("title", "")
    description = request.form.get("description", "")
    due_date    = request.form.get("dueDate", "")
    file_url    = save_file(request.files.get("file"))
    doc = {
        "title":       title,
        "description": description,
        "dueDate":     due_date,
        "fileUrl":     file_url,
        "createdBy":   request.user_id,
        "createdAt":   datetime.datetime.utcnow(),
    }
    ins = assignments.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    return jsonify(doc), 201

@app.delete("/api/assignments/<aid>")
@auth_required
def delete_assignment(aid):
    assignments.delete_one({"_id": ObjectId(aid)})
    return jsonify({"msg": "Assignment deleted"})

@app.put("/api/assignments/<aid>")
@auth_required
def update_assignment(aid):
    data = request.get_json(force=True)
    assignments.update_one({"_id": ObjectId(aid)}, {"$set": data})
    doc = assignments.find_one({"_id": ObjectId(aid)})
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  PAPERS  /api/papers
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/papers")
def get_papers():
    return jsonify([serialize(p) for p in papers_col.find().sort("createdAt", -1)])

@app.post("/api/papers")
@auth_required
def create_paper():
    title    = request.form.get("title", "")
    subject  = request.form.get("subject", "")
    year     = request.form.get("year", "")
    file_url = save_file(request.files.get("file"))
    doc = {
        "title":     title,
        "subject":   subject,
        "year":      year,
        "fileUrl":   file_url,
        "createdBy": request.user_id,
        "createdAt": datetime.datetime.utcnow(),
    }
    ins = papers_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    return jsonify(doc), 201

@app.delete("/api/papers/<pid>")
@auth_required
def delete_paper(pid):
    papers_col.delete_one({"_id": ObjectId(pid)})
    return jsonify({"msg": "Paper deleted"})

@app.put("/api/papers/<pid>")
@auth_required
def update_paper(pid):
    data = request.get_json(force=True)
    papers_col.update_one({"_id": ObjectId(pid)}, {"$set": data})
    doc = papers_col.find_one({"_id": ObjectId(pid)})
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  ANNOUNCEMENTS  /api/announcements
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/announcements")
def get_announcements():
    return jsonify([serialize(a) for a in announcements.find().sort("createdAt", -1)])

@app.post("/api/announcements")
@auth_required
def create_announcement():
    data = request.get_json(force=True)
    doc = {
        "title":     data.get("title", ""),
        "message":   data.get("message", ""),
        "createdBy": request.user_id,
        "createdAt": datetime.datetime.utcnow(),
    }
    ins = announcements.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    return jsonify(doc), 201

@app.delete("/api/announcements/<aid>")
@auth_required
def delete_announcement(aid):
    announcements.delete_one({"_id": ObjectId(aid)})
    return jsonify({"msg": "Announcement deleted"})

@app.put("/api/announcements/<aid>")
@auth_required
def update_announcement(aid):
    data = request.get_json(force=True)
    announcements.update_one({"_id": ObjectId(aid)}, {"$set": data})
    doc = announcements.find_one({"_id": ObjectId(aid)})
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  TIMETABLE  /api/timetable
# ══════════════════════════════════════════════════════════════════════════════
def serialize_tt(doc):
    """Serialize timetable doc — normalise old 'entries' field to 'slots'."""
    s = serialize(doc)
    if s is None:
        return None
    # backward-compat: old records stored period rows under 'entries' key
    if not s.get("slots") and s.get("entries"):
        s["slots"] = s["entries"]
    if "slots" not in s:
        s["slots"] = []
    return s

@app.get("/api/timetable")
def get_timetables():
    return jsonify([serialize_tt(t) for t in timetables.find().sort("createdAt", -1)])

@app.post("/api/timetable")
@auth_required
def create_timetable():
    data = request.get_json(force=True)
    # accept both 'slots' (new) and 'entries' (legacy) key names
    slots = data.get("slots") or data.get("entries") or []
    doc = {
        "title":     data.get("title", ""),
        "slots":     slots,
        "createdBy": request.user_id,
        "createdAt": datetime.datetime.utcnow(),
    }
    ins = timetables.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    return jsonify(doc), 201

@app.delete("/api/timetable/<tid>")
@auth_required
def delete_timetable(tid):
    timetables.delete_one({"_id": ObjectId(tid)})
    return jsonify({"msg": "Timetable deleted"})

@app.put("/api/timetable/<tid>")
@auth_required
def update_timetable(tid):
    data = request.get_json(force=True)
    # normalise key if client sends 'entries'
    if "entries" in data and "slots" not in data:
        data["slots"] = data.pop("entries")
    timetables.update_one({"_id": ObjectId(tid)}, {"$set": data})
    doc = timetables.find_one({"_id": ObjectId(tid)})
    return jsonify(serialize_tt(doc))

@app.post("/api/timetable/migrate")
@auth_required
def migrate_timetables():
    """One-shot: copy 'entries' -> 'slots' for all old records missing slots."""
    updated = 0
    for doc in timetables.find({"slots": {"$in": [[], None]}, "entries": {"$exists": True}}):
        timetables.update_one(
            {"_id": doc["_id"]},
            {"$set": {"slots": doc.get("entries", [])}, "$unset": {"entries": ""}}
        )
        updated += 1
    return jsonify({"msg": f"Migrated {updated} timetable records"})

# ══════════════════════════════════════════════════════════════════════════════
#  SYLLABUS  /api/syllabus
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/syllabus")
def get_syllabi():
    return jsonify([serialize(s) for s in syllabi.find().sort("createdAt", -1)])

@app.post("/api/syllabus")
@auth_required
def create_syllabus():
    data = request.get_json(force=True)
    doc = {
        "title":       data.get("title", ""),
        "subject":     data.get("subject", ""),
        "description": data.get("description", ""),
        "topics":      data.get("topics", []),
        "createdBy":   request.user_id,
        "createdAt":   datetime.datetime.utcnow(),
    }
    ins = syllabi.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    return jsonify(doc), 201

@app.delete("/api/syllabus/<sid>")
@auth_required
def delete_syllabus(sid):
    syllabi.delete_one({"_id": ObjectId(sid)})
    return jsonify({"msg": "Syllabus deleted"})

@app.put("/api/syllabus/<sid>")
@auth_required
def update_syllabus(sid):
    data = request.get_json(force=True)
    syllabi.update_one({"_id": ObjectId(sid)}, {"$set": data})
    doc = syllabi.find_one({"_id": ObjectId(sid)})
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORIES  /api/categories
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/categories")
def get_categories():
    return jsonify([serialize(c) for c in categories.find().sort("createdAt", -1)])

@app.post("/api/categories")
@auth_required
def create_category():
    data = request.get_json(force=True)
    doc = {
        "name":        data.get("name", ""),
        "description": data.get("description", ""),
        "createdBy":   request.user_id,
        "createdAt":   datetime.datetime.utcnow(),
    }
    ins = categories.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    return jsonify(doc), 201

@app.delete("/api/categories/<cid>")
@auth_required
def delete_category(cid):
    categories.delete_one({"_id": ObjectId(cid)})
    return jsonify({"msg": "Category deleted"})

@app.put("/api/categories/<cid>")
@auth_required
def update_category(cid):
    data = request.get_json(force=True)
    categories.update_one({"_id": ObjectId(cid)}, {"$set": data})
    doc = categories.find_one({"_id": ObjectId(cid)})
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  SEARCH  /api/search
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"notes": [], "assignments": [], "papers": []})
    rx = {"$regex": q, "$options": "i"}
    results = {
        "notes":       [serialize(n) for n in notes_col.find({"$or": [{"title": rx}, {"description": rx}]})],
        "assignments": [serialize(a) for a in assignments.find({"$or": [{"title": rx}, {"description": rx}]})],
        "papers":      [serialize(p) for p in papers_col.find({"$or": [{"title": rx}, {"subject": rx}]})],
    }
    return jsonify(results)

# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Student Hub Backend  (Python Flask)")
    print(f"  http://localhost:{PORT}/api")
    print("=" * 55)
    app.run(host="0.0.0.0", port=PORT, debug=False)
