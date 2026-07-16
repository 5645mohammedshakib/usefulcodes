"""
Student Hub - Python Flask Backend Server
Run: python server.py
API: http://localhost:5000
"""

import os, uuid, datetime, gzip, json, requests as http_requests
from functools import wraps
from io import BytesIO

from flask import Flask, request, jsonify, send_from_directory, Response, after_this_request
from flask_cors import CORS
from pymongo import MongoClient, DESCENDING, ASCENDING
from bson import ObjectId
import bcrypt, jwt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ─── Config ────────────────────────────────────────────────────────────────────
MONGO_URI         = os.getenv("MONGO_URI",  "mongodb://127.0.0.1:27017/student_hub")
JWT_SECRET        = os.getenv("JWT_SECRET", "student_hub_admin_supersecretkey_2026!@#")
PORT              = int(os.getenv("PORT",   5000))
UPLOAD_DIR        = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Cloudinary config (set these in Render environment variables)
CLOUDINARY_CLOUD  = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_KEY    = os.getenv("CLOUDINARY_API_KEY",    "")
CLOUDINARY_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
USE_CLOUDINARY    = bool(CLOUDINARY_CLOUD and CLOUDINARY_KEY and CLOUDINARY_SECRET)

# ─── DB Setup ──────────────────────────────────────────────────────────────────
client = MongoClient(
    MONGO_URI,
    maxPoolSize=5,          # keep pool small for free tier
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=10000,
    socketTimeoutMS=20000,
)
db = client.get_database()

users         = db["users"]
notes_col     = db["notes"]
assignments   = db["assignments"]
papers_col    = db["papers"]
announcements = db["announcements"]
timetables    = db["timetables"]
syllabi       = db["syllabi"]
categories    = db["categories"]
clicks_col    = db["clicks"]
activity_logs = db["activity_logs"]
error_logs    = db["error_logs"]
feedback_col  = db["feedback"]
settings_col  = db["settings"]
events_col        = db["events"]
subjects_col      = db["subjects"]
semesters_col     = db["semesters"]
quick_links_col   = db["quick_links"]
banners_col       = db["banners"]
notifications_col = db["notifications"]
forum_col         = db["forum"]

# ─── Indexes ───────────────────────────────────────────────────────────────────
try:
    users.create_index("email",    unique=True, sparse=True)
    users.create_index("username", unique=True, sparse=True)
    users.create_index("createdAt")
    notes_col.create_index([("title","text"),("description","text"),("category","text")])
    notes_col.create_index("createdAt")
    notes_col.create_index("category")
    notes_col.create_index("semester")
    assignments.create_index("createdAt")
    assignments.create_index("semester")
    papers_col.create_index([("title","text"),("subject","text")])
    papers_col.create_index("createdAt")
    papers_col.create_index("subject")
    papers_col.create_index("semester")
    announcements.create_index("createdAt")
    timetables.create_index("createdAt")
    syllabi.create_index("createdAt")
    categories.create_index("name")
    events_col.create_index("startDate")
    events_col.create_index("createdAt")
    subjects_col.create_index("name")
    semesters_col.create_index("number")
    quick_links_col.create_index("order")
    banners_col.create_index("order")
    banners_col.create_index("active")
    notifications_col.create_index("createdAt")
    clicks_col.create_index("resourceId", unique=True)
    clicks_col.create_index([("clicks", DESCENDING)])
    activity_logs.create_index("timestamp")
    error_logs.create_index("timestamp")
    forum_col.create_index("createdAt")
except Exception as e:
    print("Warning: Index creation issue:", e)

# ─── GZIP Compression ──────────────────────────────────────────────────────────
def gzip_response(response):
    if (response.status_code < 200 or response.status_code >= 300
            or response.direct_passthrough
            or 'gzip' not in request.headers.get('Accept-Encoding', '')):
        return response
    data = response.get_data()
    if len(data) < 500:
        return response
    buf = BytesIO()
    with gzip.GzipFile(mode='wb', fileobj=buf, compresslevel=6) as f:
        f.write(data)
    response.set_data(buf.getvalue())
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length']   = len(response.get_data())
    return response

app.after_request(gzip_response)

# ─── Cache Control ─────────────────────────────────────────────────────────────
def add_cache_headers(response, seconds=60):
    response.headers['Cache-Control'] = f'public, max-age={seconds}'
    return response

# ─── Helpers ───────────────────────────────────────────────────────────────────
def serialize(doc):
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

def is_admin(user_id: str) -> bool:
    u = users.find_one({"_id": ObjectId(user_id)})
    return u is not None and u.get("role") == "admin"

def log_admin_action(action, details):
    try:
        activity_logs.insert_one({
            "action": action, "details": details,
            "adminId": request.user_id,
            "timestamp": datetime.datetime.utcnow()
        })
    except Exception:
        pass

def save_file(file_obj) -> str | None:
    """Upload file to Cloudinary (permanent) or local disk (fallback)."""
    if not file_obj or not file_obj.filename:
        return None

    if USE_CLOUDINARY:
        try:
            import hmac, hashlib, time
            ts        = str(int(time.time()))
            folder    = "student_hub"
            params    = f"folder={folder}&timestamp={ts}"
            sig_str   = params + CLOUDINARY_SECRET
            signature = hashlib.sha1(sig_str.encode()).hexdigest()
            upload_url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD}/auto/upload"
            resp = http_requests.post(upload_url, data={
                "api_key":   CLOUDINARY_KEY,
                "timestamp": ts,
                "folder":    folder,
                "signature": signature,
            }, files={"file": (file_obj.filename, file_obj.stream, file_obj.content_type)}, timeout=60)
            if resp.ok:
                return resp.json().get("secure_url", "")
        except Exception as e:
            print(f"Cloudinary upload failed, falling back to local: {e}")

    # Fallback: local disk (works locally, ephemeral on Render free tier)
    ext      = os.path.splitext(file_obj.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    file_obj.save(os.path.join(UPLOAD_DIR, filename))
    return f"/uploads/{filename}"

# ─── Static uploads ────────────────────────────────────────────────────────────
@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    resp = send_from_directory(UPLOAD_DIR, filename)
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp

# ─── Health / Keep-Alive ───────────────────────────────────────────────────────
@app.get("/")
@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "app": "Student Hub API", "version": "2.0", "time": datetime.datetime.utcnow().isoformat()})

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH  /api/auth
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/auth/register")
def register():
    data     = request.get_json(force=True)
    name     = data.get("name", "").strip()
    email    = data.get("email", "").strip().lower()
    username = data.get("username", email).strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"errors": [{"msg": "Email and password required"}]}), 400
    if len(password) < 6:
        return jsonify({"errors": [{"msg": "Password must be at least 6 characters"}]}), 400
    if users.find_one({"$or": [{"email": email}, {"username": username}]}):
        return jsonify({"errors": [{"msg": "User already exists"}]}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    uid = users.insert_one({
        "name": name or username, "email": email, "username": username,
        "password": hashed, "role": "user",
        "createdAt": datetime.datetime.utcnow(),
    }).inserted_id
    return jsonify({"token": make_token(str(uid))})

@app.post("/api/auth/login")
def login():
    data = request.get_json(force=True)
    eid  = (data.get("email") or data.get("username") or "").strip().lower()
    pwd  = data.get("password", "")
    user = users.find_one({"$or": [{"email": eid}, {"username": eid}]})
    if not user or not bcrypt.checkpw(pwd.encode(), user["password"].encode()):
        return jsonify({"errors": [{"msg": "Invalid credentials"}]}), 400
    
    users.update_one({"_id": user["_id"]}, {"$set": {"lastLogin": datetime.datetime.utcnow()}})
    return jsonify({"token": make_token(str(user["_id"]))})

@app.get("/api/auth/me")
@auth_required
def get_me():
    users.update_one({"_id": ObjectId(request.user_id)}, {"$set": {"lastLogin": datetime.datetime.utcnow()}})
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
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    
    all_users = []
    for u in users.find({}, {"password": 0}).sort("createdAt", DESCENDING):
        doc = serialize(u)
        if not doc.get("lastLogin") and doc.get("createdAt"):
            doc["lastLogin"] = doc["createdAt"]
        all_users.append(doc)
    return jsonify(all_users)

@app.delete("/api/users/<user_id>")
@auth_required
def delete_user(user_id):
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    users.delete_one({"_id": ObjectId(user_id)})
    return jsonify({"msg": "User deleted"})

# ══════════════════════════════════════════════════════════════════════════════
#  NOTES  /api/notes
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/notes")
def get_notes():
    limit    = int(request.args.get("limit", 50))
    skip     = int(request.args.get("skip", 0))
    category = request.args.get("category", "")
    q        = request.args.get("q", "").strip()
    query    = {}
    if category:
        query["category"] = category
    if q:
        query["$text"] = {"$search": q}
    cursor = notes_col.find(query).sort("createdAt", DESCENDING).skip(skip).limit(limit)
    resp = jsonify([serialize(n) for n in cursor])
    return add_cache_headers(resp, 30)

@app.post("/api/notes")
@auth_required
def create_note():
    title       = request.form.get("title", "")
    description = request.form.get("description", "")
    category    = request.form.get("category", "")
    file_url    = save_file(request.files.get("file"))
    doc = {
        "title": title, "description": description, "category": category,
        "fileUrl": file_url, "createdBy": request.user_id,
        "createdAt": datetime.datetime.utcnow(), "downloads": 0,
    }
    ins = notes_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_NOTE", f"Created note: {title}")
    return jsonify(doc), 201

@app.delete("/api/notes/<nid>")
@auth_required
def delete_note(nid):
    notes_col.delete_one({"_id": ObjectId(nid)})
    log_admin_action("DELETE_NOTE", f"Deleted note: {nid}")
    return jsonify({"msg": "Note deleted"})

@app.put("/api/notes/<nid>")
@auth_required
def update_note(nid):
    data = request.get_json(force=True)
    notes_col.update_one({"_id": ObjectId(nid)}, {"$set": data})
    doc = notes_col.find_one({"_id": ObjectId(nid)})
    log_admin_action("UPDATE_NOTE", f"Updated note: {nid}")
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  ASSIGNMENTS  /api/assignments
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/assignments")
def get_assignments():
    limit  = int(request.args.get("limit", 50))
    skip   = int(request.args.get("skip", 0))
    cursor = assignments.find({}).sort("createdAt", DESCENDING).skip(skip).limit(limit)
    resp = jsonify([serialize(a) for a in cursor])
    return add_cache_headers(resp, 30)

@app.post("/api/assignments")
@auth_required
def create_assignment():
    title       = request.form.get("title", "")
    description = request.form.get("description", "")
    due_date    = request.form.get("dueDate", "")
    file_url    = save_file(request.files.get("file"))
    doc = {
        "title": title, "description": description, "dueDate": due_date,
        "fileUrl": file_url, "createdBy": request.user_id,
        "createdAt": datetime.datetime.utcnow(),
    }
    ins = assignments.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_ASSIGNMENT", f"Created assignment: {title}")
    return jsonify(doc), 201

@app.delete("/api/assignments/<aid>")
@auth_required
def delete_assignment(aid):
    assignments.delete_one({"_id": ObjectId(aid)})
    log_admin_action("DELETE_ASSIGNMENT", f"Deleted: {aid}")
    return jsonify({"msg": "Assignment deleted"})

@app.put("/api/assignments/<aid>")
@auth_required
def update_assignment(aid):
    data = request.get_json(force=True)
    assignments.update_one({"_id": ObjectId(aid)}, {"$set": data})
    doc = assignments.find_one({"_id": ObjectId(aid)})
    log_admin_action("UPDATE_ASSIGNMENT", f"Updated: {aid}")
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  PAPERS  /api/papers
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/papers")
def get_papers():
    limit   = int(request.args.get("limit", 50))
    skip    = int(request.args.get("skip", 0))
    subject = request.args.get("subject", "")
    q       = request.args.get("q", "").strip()
    query   = {}
    if subject:
        query["subject"] = subject
    if q:
        query["$text"] = {"$search": q}
    cursor = papers_col.find(query).sort("createdAt", DESCENDING).skip(skip).limit(limit)
    resp = jsonify([serialize(p) for p in cursor])
    return add_cache_headers(resp, 30)

@app.post("/api/papers")
@auth_required
def create_paper():
    title    = request.form.get("title", "")
    subject  = request.form.get("subject", "")
    year     = request.form.get("year", "")
    file_url = save_file(request.files.get("file"))
    doc = {
        "title": title, "subject": subject, "year": year,
        "fileUrl": file_url, "createdBy": request.user_id,
        "createdAt": datetime.datetime.utcnow(),
    }
    ins = papers_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_PAPER", f"Created paper: {title}")
    return jsonify(doc), 201

@app.delete("/api/papers/<pid>")
@auth_required
def delete_paper(pid):
    papers_col.delete_one({"_id": ObjectId(pid)})
    log_admin_action("DELETE_PAPER", f"Deleted: {pid}")
    return jsonify({"msg": "Paper deleted"})

@app.put("/api/papers/<pid>")
@auth_required
def update_paper(pid):
    data = request.get_json(force=True)
    papers_col.update_one({"_id": ObjectId(pid)}, {"$set": data})
    doc = papers_col.find_one({"_id": ObjectId(pid)})
    log_admin_action("UPDATE_PAPER", f"Updated: {pid}")
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  ANNOUNCEMENTS  /api/announcements
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/announcements")
def get_announcements():
    limit  = int(request.args.get("limit", 50))
    skip   = int(request.args.get("skip", 0))
    cursor = announcements.find({}).sort("createdAt", DESCENDING).skip(skip).limit(limit)
    resp = jsonify([serialize(a) for a in cursor])
    return add_cache_headers(resp, 15)

@app.post("/api/announcements")
@auth_required
def create_announcement():
    data = request.get_json(force=True)
    doc = {
        "title": data.get("title", ""), "message": data.get("message", ""),
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = announcements.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_ANNOUNCEMENT", f"Posted: {data.get('title')}")
    return jsonify(doc), 201

@app.delete("/api/announcements/<aid>")
@auth_required
def delete_announcement(aid):
    announcements.delete_one({"_id": ObjectId(aid)})
    log_admin_action("DELETE_ANNOUNCEMENT", f"Deleted: {aid}")
    return jsonify({"msg": "Announcement deleted"})

@app.put("/api/announcements/<aid>")
@auth_required
def update_announcement(aid):
    data = request.get_json(force=True)
    announcements.update_one({"_id": ObjectId(aid)}, {"$set": data})
    doc = announcements.find_one({"_id": ObjectId(aid)})
    log_admin_action("UPDATE_ANNOUNCEMENT", f"Updated: {aid}")
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  TIMETABLE  /api/timetable
# ══════════════════════════════════════════════════════════════════════════════
def serialize_tt(doc):
    s = serialize(doc)
    if s is None:
        return None
    if not s.get("slots") and s.get("entries"):
        s["slots"] = s["entries"]
    if "slots" not in s:
        s["slots"] = []
    return s

@app.get("/api/timetable")
def get_timetables():
    resp = jsonify([serialize_tt(t) for t in timetables.find().sort("createdAt", DESCENDING)])
    return add_cache_headers(resp, 60)

@app.post("/api/timetable")
@auth_required
def create_timetable():
    data  = request.get_json(force=True)
    slots = data.get("slots") or data.get("entries") or []
    doc = {
        "title": data.get("title", ""), "slots": slots,
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = timetables.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_TIMETABLE", f"Saved timetable: {data.get('title')}")
    return jsonify(doc), 201

@app.delete("/api/timetable/<tid>")
@auth_required
def delete_timetable(tid):
    timetables.delete_one({"_id": ObjectId(tid)})
    log_admin_action("DELETE_TIMETABLE", f"Deleted: {tid}")
    return jsonify({"msg": "Timetable deleted"})

@app.put("/api/timetable/<tid>")
@auth_required
def update_timetable(tid):
    data = request.get_json(force=True)
    if "entries" in data and "slots" not in data:
        data["slots"] = data.pop("entries")
    timetables.update_one({"_id": ObjectId(tid)}, {"$set": data})
    doc = timetables.find_one({"_id": ObjectId(tid)})
    log_admin_action("UPDATE_TIMETABLE", f"Updated: {tid}")
    return jsonify(serialize_tt(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  SYLLABUS  /api/syllabus
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/syllabus")
def get_syllabi():
    resp = jsonify([serialize(s) for s in syllabi.find().sort("createdAt", DESCENDING)])
    return add_cache_headers(resp, 60)

@app.post("/api/syllabus")
@auth_required
def create_syllabus():
    data = request.get_json(force=True)
    doc = {
        "title": data.get("title", ""), "subject": data.get("subject", ""),
        "description": data.get("description", ""), "topics": data.get("topics", []),
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = syllabi.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_SYLLABUS", f"Created syllabus: {data.get('title')}")
    return jsonify(doc), 201

@app.delete("/api/syllabus/<sid>")
@auth_required
def delete_syllabus(sid):
    syllabi.delete_one({"_id": ObjectId(sid)})
    log_admin_action("DELETE_SYLLABUS", f"Deleted: {sid}")
    return jsonify({"msg": "Syllabus deleted"})

@app.put("/api/syllabus/<sid>")
@auth_required
def update_syllabus(sid):
    data = request.get_json(force=True)
    syllabi.update_one({"_id": ObjectId(sid)}, {"$set": data})
    doc = syllabi.find_one({"_id": ObjectId(sid)})
    log_admin_action("UPDATE_SYLLABUS", f"Updated: {sid}")
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  CATEGORIES  /api/categories
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/categories")
def get_categories():
    resp = jsonify([serialize(c) for c in categories.find().sort("createdAt", DESCENDING)])
    return add_cache_headers(resp, 120)

@app.post("/api/categories")
@auth_required
def create_category():
    data = request.get_json(force=True)
    doc = {
        "name": data.get("name", ""), "description": data.get("description", ""),
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = categories.insert_one(doc)
    doc["_id"] = str(ins.inserted_id)
    doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_CATEGORY", f"Created: {data.get('name')}")
    return jsonify(doc), 201

@app.delete("/api/categories/<cid>")
@auth_required
def delete_category(cid):
    categories.delete_one({"_id": ObjectId(cid)})
    log_admin_action("DELETE_CATEGORY", f"Deleted: {cid}")
    return jsonify({"msg": "Category deleted"})

@app.put("/api/categories/<cid>")
@auth_required
def update_category(cid):
    data = request.get_json(force=True)
    categories.update_one({"_id": ObjectId(cid)}, {"$set": data})
    doc = categories.find_one({"_id": ObjectId(cid)})
    log_admin_action("UPDATE_CATEGORY", f"Updated: {cid}")
    return jsonify(serialize(doc))

# ══════════════════════════════════════════════════════════════════════════════
#  SEARCH  /api/search
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"notes": [], "assignments": [], "papers": [], "syllabus": []})
    rx = {"$regex": q, "$options": "i"}
    results = {
        "notes":       [serialize(n) for n in notes_col.find({"$or": [{"title": rx}, {"description": rx}, {"category": rx}]}).limit(10)],
        "assignments": [serialize(a) for a in assignments.find({"$or": [{"title": rx}, {"description": rx}]}).limit(5)],
        "papers":      [serialize(p) for p in papers_col.find({"$or": [{"title": rx}, {"subject": rx}]}).limit(10)],
        "syllabus":    [serialize(s) for s in syllabi.find({"$or": [{"title": rx}, {"subject": rx}]}).limit(5)],
    }
    return jsonify(results)

# ══════════════════════════════════════════════════════════════════════════════
#  ANALYTICS  /api/analytics
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/analytics/click")
def track_click():
    data = request.get_json(force=True)
    rid  = data.get("resourceId")
    type_ = data.get("type")
    if not rid:
        return jsonify({"msg": "resourceId required"}), 400
    clicks_col.update_one(
        {"resourceId": rid},
        {"$inc": {"clicks": 1}, "$set": {"type": type_, "updatedAt": datetime.datetime.utcnow()}},
        upsert=True
    )
    # Also increment downloads counter on the doc
    if type_ == "note":
        notes_col.update_one({"_id": ObjectId(rid)}, {"$inc": {"downloads": 1}}, upsert=False)
    return jsonify({"status": "ok"})

# ══════════════════════════════════════════════════════════════════════════════
#  FEEDBACK  /api/feedback
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/feedback")
def submit_feedback():
    data = request.get_json(force=True)
    doc = {
        "type": data.get("type", "feedback"),
        "text": data.get("text", ""),
        "userId": data.get("userId", "anonymous"),
        "timestamp": datetime.datetime.utcnow(),
    }
    feedback_col.insert_one(doc)
    return jsonify({"msg": "Feedback received. Thank you!"})

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN  /api/admin
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/stats")
@auth_required
def get_admin_stats():
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    total_students   = users.count_documents({"role": {"$ne": "admin"}})
    total_notes      = notes_col.count_documents({})
    total_assignments = assignments.count_documents({})
    total_papers     = papers_col.count_documents({})
    total_ann        = announcements.count_documents({})
    total_timetables = timetables.count_documents({})
    total_syllabi    = syllabi.count_documents({})
    total_categories = categories.count_documents({})

    # Student growth per month (last 6 months)
    six_months_ago = datetime.datetime.utcnow() - datetime.timedelta(days=180)
    pipeline = [
        {"$match": {"createdAt": {"$gte": six_months_ago}, "role": {"$ne": "admin"}}},
        {"$group": {"_id": {"year": {"$year": "$createdAt"}, "month": {"$month": "$createdAt"}}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    growth = list(users.aggregate(pipeline))
    growth_data = [{"month": f"{g['_id']['year']}-{g['_id']['month']:02d}", "count": g["count"]} for g in growth]

    # Storage
    total_size = sum(os.path.getsize(os.path.join(UPLOAD_DIR, f))
                     for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))) if os.path.exists(UPLOAD_DIR) else 0
    file_count = len([f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]) if os.path.exists(UPLOAD_DIR) else 0

    return jsonify({
        "totalStudents":    total_students,
        "totalNotes":       total_notes,
        "totalAssignments": total_assignments,
        "totalPapers":      total_papers,
        "totalAnnouncements": total_ann,
        "totalTimetables":  total_timetables,
        "totalSyllabi":     total_syllabi,
        "totalCategories":  total_categories,
        "storageUsed":      total_size,
        "fileCount":        file_count,
        "maxStorage":       100 * 1024 * 1024,
        "studentGrowth":    growth_data,
    })

@app.get("/api/admin/analytics")
@auth_required
def get_admin_analytics():
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    total_students   = users.count_documents({"role": {"$ne": "admin"}})
    total_notes      = notes_col.count_documents({})
    total_assignments = assignments.count_documents({})
    total_papers     = papers_col.count_documents({})

    top_clicked = list(clicks_col.find().sort("clicks", DESCENDING).limit(10))
    popular_list = []
    for click in top_clicked:
        rid   = click["resourceId"]
        ctype = click["type"]
        clicks = click["clicks"]
        name  = "Unknown"
        try:
            if ctype == "note":
                doc = notes_col.find_one({"_id": ObjectId(rid)})
                if doc: name = doc.get("title", "")
            elif ctype == "paper":
                doc = papers_col.find_one({"_id": ObjectId(rid)})
                if doc: name = f"{doc.get('title')} ({doc.get('subject','')})"
            elif ctype == "assignment":
                doc = assignments.find_one({"_id": ObjectId(rid)})
                if doc: name = doc.get("title", "")
        except Exception:
            pass
        popular_list.append({"resourceId": rid, "type": ctype, "clicks": clicks, "title": name})

    # Most downloaded notes
    top_notes = list(notes_col.find({}, {"title": 1, "downloads": 1, "category": 1}).sort("downloads", DESCENDING).limit(10))

    return jsonify({
        "totalStudents":    total_students,
        "totalNotes":       total_notes,
        "totalAssignments": total_assignments,
        "totalPapers":      total_papers,
        "popular":          popular_list,
        "topNotes":         [serialize(n) for n in top_notes],
    })

@app.get("/api/admin/storage")
@auth_required
def get_storage():
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    total_size = 0
    file_count = 0
    if os.path.exists(UPLOAD_DIR):
        for f in os.listdir(UPLOAD_DIR):
            fp = os.path.join(UPLOAD_DIR, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
                file_count += 1
    return jsonify({"totalSize": total_size, "fileCount": file_count, "maxStorage": 100 * 1024 * 1024})

@app.get("/api/admin/logs")
@auth_required
def get_logs():
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    activities = [serialize(log) for log in activity_logs.find().sort("timestamp", DESCENDING).limit(50)]
    admin_ids  = list(set([log["adminId"] for log in activities if log.get("adminId")]))
    admins = {}
    if admin_ids:
        admins = {str(u["_id"]): u["name"] for u in users.find({"_id": {"$in": [ObjectId(aid) for aid in admin_ids]}})}
    for log in activities:
        log["adminName"] = admins.get(log.get("adminId"), "Admin")
    errors = [serialize(log) for log in error_logs.find().sort("timestamp", DESCENDING).limit(50)]
    return jsonify({"activities": activities, "errors": errors})

@app.get("/api/admin/feedback")
@auth_required
def get_feedback():
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    items = [serialize(f) for f in feedback_col.find().sort("timestamp", DESCENDING).limit(100)]
    return jsonify(items)

@app.post("/api/admin/bulk-upload")
@auth_required
def bulk_upload():
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    data  = request.get_json(force=True)
    type_ = data.get("type")
    items = data.get("items", [])
    if not type_ or not items:
        return jsonify({"msg": "Type and items required"}), 400
    for item in items:
        doc = {
            "title": item.get("title", ""), "fileUrl": item.get("fileUrl"),
            "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow()
        }
        if type_ == "note":
            doc["description"] = item.get("description", "")
            doc["category"]    = item.get("category", "")
            doc["downloads"]   = 0
            notes_col.insert_one(doc)
        elif type_ == "paper":
            doc["subject"] = item.get("subject", "")
            doc["year"]    = item.get("year", "")
            papers_col.insert_one(doc)
    log_admin_action("BULK_UPLOAD", f"Bulk uploaded {len(items)} {type_} items")
    return jsonify({"msg": f"Successfully uploaded {len(items)} {type_} items."})

@app.post("/api/timetable/migrate")
@auth_required
def migrate_timetables():
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    updated = 0
    for doc in timetables.find({"slots": {"$in": [[], None]}, "entries": {"$exists": True}}):
        timetables.update_one(
            {"_id": doc["_id"]},
            {"$set": {"slots": doc.get("entries", [])}, "$unset": {"entries": ""}}
        )
        updated += 1
    return jsonify({"msg": f"Migrated {updated} records"})

@app.get("/api/settings")
def get_student_settings():
    s = settings_col.find_one({"key": "student_features"})
    default_features = [
        { "key": "announcements", "title": "Announcements", "icon": "megaphone", "type": "builtin", "enabled": True },
        { "key": "notes", "title": "Study Notes", "icon": "notebook-text", "type": "builtin", "enabled": True },
        { "key": "assignments", "title": "Assignments", "icon": "clipboard-list", "type": "builtin", "enabled": True },
        { "key": "timetable", "title": "Timetable", "icon": "calendar-days", "type": "builtin", "enabled": True },
        { "key": "syllabus", "title": "Syllabus", "icon": "book-open", "type": "builtin", "enabled": True },
        { "key": "papers", "title": "Previous Papers", "icon": "file-text", "type": "builtin", "enabled": True },
        { "key": "focus", "title": "Focus Zone", "icon": "timer", "type": "builtin", "enabled": True }
    ]
    if not s:
        default = {
            "key": "student_features",
            "search": True, "bookmarks": True, "focus": True,
            "papers": True, "syllabus": True, "assignments": True,
            "announcements": True, "timetable": True, "notes": True,
            "events": True, "quickLinks": True, "banners": True,
            "feedback": True, "downloads": True,
            "directDownloads": True, "maintenanceMode": False,
            "emergencyBanner": False, "feedbackEnabled": True, "streaksEnabled": True,
            "broadcastMessage": "Welcome to Student Hub Portal!",
            "homePageSections": ["announcements","notes","assignments","papers","timetable","syllabus","events","quickLinks"],
            "featureVisibility": {},
            "appVersion": "1.0.0", "appUpdateMessage": "", "appUpdateRequired": False,
            "features": default_features
        }
        settings_col.insert_one(default)
        s = default
    else:
        if "features" not in s:
            s["features"] = default_features
            settings_col.update_one({"key": "student_features"}, {"$set": {"features": default_features}})
    return jsonify(serialize(s))

@app.post("/api/admin/settings")
@auth_required
def update_student_settings():
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    updates = {}
    bool_keys = [
        "search", "bookmarks", "focus", "papers", "syllabus",
        "assignments", "announcements", "timetable", "notes",
        "events", "quickLinks", "banners", "feedback", "downloads",
        "directDownloads", "maintenanceMode", "emergencyBanner",
        "feedbackEnabled", "streaksEnabled", "appUpdateRequired"
    ]
    for k in bool_keys:
        if k in data:
            updates[k] = bool(data[k])
    str_keys = ["broadcastMessage", "appVersion", "appUpdateMessage"]
    for k in str_keys:
        if k in data:
            updates[k] = str(data[k])
    if "homePageSections" in data and isinstance(data["homePageSections"], list):
        updates["homePageSections"] = data["homePageSections"]
    if "featureVisibility" in data and isinstance(data["featureVisibility"], dict):
        updates["featureVisibility"] = data["featureVisibility"]
    if "features" in data and isinstance(data["features"], list):
        updates["features"] = data["features"]
    settings_col.update_one({"key": "student_features"}, {"$set": updates}, upsert=True)
    log_admin_action("UPDATE_SETTINGS", "Updated student portal settings")
    return jsonify({"status": "ok", "msg": "Settings updated successfully!"})

# ══════════════════════════════════════════════════════════════════════════════
#  EVENTS  /api/events
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/events")
def get_events():
    limit  = int(request.args.get("limit", 50))
    skip   = int(request.args.get("skip", 0))
    cursor = events_col.find({}).sort("startDate", ASCENDING).skip(skip).limit(limit)
    resp = jsonify([serialize(e) for e in cursor])
    return add_cache_headers(resp, 30)

@app.post("/api/events")
@auth_required
def create_event():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    doc = {
        "title": data.get("title", ""), "description": data.get("description", ""),
        "startDate": data.get("startDate", ""), "endDate": data.get("endDate", ""),
        "type": data.get("type", "general"), "color": data.get("color", "#7c3aed"),
        "location": data.get("location", ""), "semester": data.get("semester", "all"),
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = events_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id); doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_EVENT", f"Created event: {data.get('title')}")
    return jsonify(doc), 201

@app.delete("/api/events/<eid>")
@auth_required
def delete_event(eid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    events_col.delete_one({"_id": ObjectId(eid)})
    log_admin_action("DELETE_EVENT", f"Deleted event: {eid}")
    return jsonify({"msg": "Event deleted"})

@app.put("/api/events/<eid>")
@auth_required
def update_event(eid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    events_col.update_one({"_id": ObjectId(eid)}, {"$set": data})
    return jsonify(serialize(events_col.find_one({"_id": ObjectId(eid)})))

# ══════════════════════════════════════════════════════════════════════════════
#  SUBJECTS  /api/subjects
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/subjects")
def get_subjects():
    semester = request.args.get("semester", "")
    query = {"semester": semester} if semester else {}
    resp = jsonify([serialize(s) for s in subjects_col.find(query).sort("name", ASCENDING)])
    return add_cache_headers(resp, 120)

@app.post("/api/subjects")
@auth_required
def create_subject():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    doc = {
        "name": data.get("name", ""), "code": data.get("code", ""),
        "semester": data.get("semester", ""), "branch": data.get("branch", "all"),
        "credits": data.get("credits", 0), "description": data.get("description", ""),
        "active": data.get("active", True),
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = subjects_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id); doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_SUBJECT", f"Created subject: {data.get('name')}")
    return jsonify(doc), 201

@app.delete("/api/subjects/<sid>")
@auth_required
def delete_subject(sid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    subjects_col.delete_one({"_id": ObjectId(sid)})
    log_admin_action("DELETE_SUBJECT", f"Deleted subject: {sid}")
    return jsonify({"msg": "Subject deleted"})

@app.put("/api/subjects/<sid>")
@auth_required
def update_subject(sid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    subjects_col.update_one({"_id": ObjectId(sid)}, {"$set": data})
    return jsonify(serialize(subjects_col.find_one({"_id": ObjectId(sid)})))

# ══════════════════════════════════════════════════════════════════════════════
#  SEMESTERS  /api/semesters
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/semesters")
def get_semesters():
    resp = jsonify([serialize(s) for s in semesters_col.find().sort("number", ASCENDING)])
    return add_cache_headers(resp, 120)

@app.post("/api/semesters")
@auth_required
def create_semester():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    num = data.get("number")
    if not num: return jsonify({"msg": "Semester number required"}), 400
    doc = {
        "number": int(num), "label": data.get("label", f"Semester {num}"),
        "startDate": data.get("startDate", ""), "endDate": data.get("endDate", ""),
        "active": data.get("active", True),
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = semesters_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id); doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_SEMESTER", f"Created semester {num}")
    return jsonify(doc), 201

@app.delete("/api/semesters/<sid>")
@auth_required
def delete_semester(sid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    semesters_col.delete_one({"_id": ObjectId(sid)})
    log_admin_action("DELETE_SEMESTER", f"Deleted semester: {sid}")
    return jsonify({"msg": "Semester deleted"})

@app.put("/api/semesters/<sid>")
@auth_required
def update_semester(sid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    semesters_col.update_one({"_id": ObjectId(sid)}, {"$set": data})
    return jsonify(serialize(semesters_col.find_one({"_id": ObjectId(sid)})))

# ══════════════════════════════════════════════════════════════════════════════
#  QUICK LINKS  /api/quick-links
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/quick-links")
def get_quick_links():
    resp = jsonify([serialize(q) for q in quick_links_col.find({"active": {"$ne": False}}).sort("order", ASCENDING)])
    return add_cache_headers(resp, 60)

@app.get("/api/quick-links/all")
@auth_required
def get_quick_links_all():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    return jsonify([serialize(q) for q in quick_links_col.find().sort("order", ASCENDING)])

@app.post("/api/quick-links")
@auth_required
def create_quick_link():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    doc = {
        "title": data.get("title", ""), "url": data.get("url", ""),
        "icon": data.get("icon", "link"), "color": data.get("color", "#7c3aed"),
        "description": data.get("description", ""),
        "order": data.get("order", quick_links_col.count_documents({})),
        "active": data.get("active", True), "openInNewTab": data.get("openInNewTab", True),
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = quick_links_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id); doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_QUICK_LINK", f"Created quick link: {data.get('title')}")
    return jsonify(doc), 201

@app.delete("/api/quick-links/<lid>")
@auth_required
def delete_quick_link(lid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    quick_links_col.delete_one({"_id": ObjectId(lid)})
    log_admin_action("DELETE_QUICK_LINK", f"Deleted: {lid}")
    return jsonify({"msg": "Quick link deleted"})

@app.put("/api/quick-links/<lid>")
@auth_required
def update_quick_link(lid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    quick_links_col.update_one({"_id": ObjectId(lid)}, {"$set": data})
    return jsonify(serialize(quick_links_col.find_one({"_id": ObjectId(lid)})))

# ══════════════════════════════════════════════════════════════════════════════
#  BANNERS  /api/banners
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/banners")
def get_banners():
    resp = jsonify([serialize(b) for b in banners_col.find({"active": True}).sort("order", ASCENDING)])
    return add_cache_headers(resp, 30)

@app.get("/api/banners/all")
@auth_required
def get_banners_all():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    return jsonify([serialize(b) for b in banners_col.find().sort("order", ASCENDING)])

@app.post("/api/banners")
@auth_required
def create_banner():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    doc = {
        "title": data.get("title", ""), "subtitle": data.get("subtitle", ""),
        "imageUrl": data.get("imageUrl", ""), "linkUrl": data.get("linkUrl", ""),
        "bgColor": data.get("bgColor", "#7c3aed"), "textColor": data.get("textColor", "#ffffff"),
        "type": data.get("type", "info"),
        "order": data.get("order", banners_col.count_documents({})),
        "active": data.get("active", True),
        "showFrom": data.get("showFrom", ""), "showUntil": data.get("showUntil", ""),
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    }
    ins = banners_col.insert_one(doc)
    doc["_id"] = str(ins.inserted_id); doc["createdAt"] = doc["createdAt"].isoformat()
    log_admin_action("CREATE_BANNER", f"Created banner: {data.get('title')}")
    return jsonify(doc), 201

@app.delete("/api/banners/<bid>")
@auth_required
def delete_banner(bid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    banners_col.delete_one({"_id": ObjectId(bid)})
    log_admin_action("DELETE_BANNER", f"Deleted: {bid}")
    return jsonify({"msg": "Banner deleted"})

@app.put("/api/banners/<bid>")
@auth_required
def update_banner(bid):
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    banners_col.update_one({"_id": ObjectId(bid)}, {"$set": data})
    return jsonify(serialize(banners_col.find_one({"_id": ObjectId(bid)})))

# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS  /api/admin/notifications
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/notifications")
@auth_required
def get_notifications():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    items = [serialize(n) for n in notifications_col.find().sort("createdAt", DESCENDING).limit(100)]
    return jsonify(items)

@app.post("/api/admin/send-notification")
@auth_required
def send_notification():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    title = data.get("title", ""); message = data.get("message", "")
    target = data.get("target", "all")
    if not title or not message:
        return jsonify({"msg": "Title and message required"}), 400
    announcements.insert_one({
        "title": title, "message": message, "type": "notification", "target": target,
        "createdBy": request.user_id, "createdAt": datetime.datetime.utcnow(),
    })
    notifications_col.insert_one({
        "title": title, "message": message, "target": target,
        "sentBy": request.user_id, "createdAt": datetime.datetime.utcnow(), "status": "delivered"
    })
    log_admin_action("SEND_NOTIFICATION", f"Sent: {title} to {target}")
    return jsonify({"msg": f"Notification sent to {target}!", "status": "ok"})

# ══════════════════════════════════════════════════════════════════════════════
#  BULK DELETE  /api/admin/bulk-delete
# ══════════════════════════════════════════════════════════════════════════════
ALLOWED_DELETE_COLS = {
    "notes": notes_col, "assignments": assignments, "papers": papers_col,
    "announcements": announcements, "timetables": timetables, "syllabi": syllabi,
    "categories": categories, "events": events_col, "subjects": subjects_col,
    "quick_links": quick_links_col, "banners": banners_col,
}

@app.post("/api/admin/bulk-delete")
@auth_required
def bulk_delete():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    col_name = data.get("collection")
    ids = data.get("ids", [])
    delete_all = data.get("deleteAll", False)
    if col_name not in ALLOWED_DELETE_COLS:
        return jsonify({"msg": "Invalid collection"}), 400
    col = ALLOWED_DELETE_COLS[col_name]
    if delete_all:
        deleted = col.delete_many({}).deleted_count
    elif ids:
        oids = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
        deleted = col.delete_many({"_id": {"$in": oids}}).deleted_count
    else:
        return jsonify({"msg": "Provide ids or deleteAll=true"}), 400
    log_admin_action("BULK_DELETE", f"Deleted {deleted} from {col_name}")
    return jsonify({"msg": f"Deleted {deleted} items from {col_name}", "deleted": deleted})

# ══════════════════════════════════════════════════════════════════════════════
#  FEATURE VISIBILITY  /api/admin/feature-visibility
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/feature-visibility")
@auth_required
def get_feature_visibility():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    s = settings_col.find_one({"key": "student_features"}) or {}
    return jsonify(s.get("featureVisibility", {}))

@app.post("/api/admin/feature-visibility")
@auth_required
def set_feature_visibility():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    settings_col.update_one({"key": "student_features"}, {"$set": {"featureVisibility": data}}, upsert=True)
    log_admin_action("UPDATE_FEATURE_VISIBILITY", "Updated per-semester feature visibility")
    return jsonify({"status": "ok", "msg": "Feature visibility updated!"})

# ══════════════════════════════════════════════════════════════════════════════
#  APP VERSION  /api/admin/app-version
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/app-version")
@auth_required
def get_app_version():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    s = settings_col.find_one({"key": "student_features"}) or {}
    return jsonify({
        "appVersion": s.get("appVersion", "1.0.0"),
        "appUpdateMessage": s.get("appUpdateMessage", ""),
        "appUpdateRequired": s.get("appUpdateRequired", False),
    })

@app.post("/api/admin/app-version")
@auth_required
def update_app_version():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    data = request.get_json(force=True)
    updates = {}
    if "appVersion" in data: updates["appVersion"] = str(data["appVersion"])
    if "appUpdateMessage" in data: updates["appUpdateMessage"] = str(data["appUpdateMessage"])
    if "appUpdateRequired" in data: updates["appUpdateRequired"] = bool(data["appUpdateRequired"])
    settings_col.update_one({"key": "student_features"}, {"$set": updates}, upsert=True)
    log_admin_action("UPDATE_APP_VERSION", f"Updated app version to {data.get('appVersion')}")
    return jsonify({"status": "ok", "msg": "App version updated!"})

# ══════════════════════════════════════════════════════════════════════════════
#  FULL STATS  /api/admin/full-stats
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/full-stats")
@auth_required
def get_full_stats():
    if not is_admin(request.user_id): return jsonify({"msg": "Admin required"}), 403
    six_months_ago = datetime.datetime.utcnow() - datetime.timedelta(days=180)
    pipeline = [
        {"$match": {"createdAt": {"$gte": six_months_ago}, "role": {"$ne": "admin"}}},
        {"$group": {"_id": {"year": {"$year": "$createdAt"}, "month": {"$month": "$createdAt"}}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    growth_data = [{"month": f"{g['_id']['year']}-{g['_id']['month']:02d}", "count": g["count"]} for g in users.aggregate(pipeline)]
    total_size = sum(os.path.getsize(os.path.join(UPLOAD_DIR, f))
                     for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))) if os.path.exists(UPLOAD_DIR) else 0
    file_count = len([f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))]) if os.path.exists(UPLOAD_DIR) else 0
    return jsonify({
        "totalStudents": users.count_documents({"role": {"$ne": "admin"}}),
        "totalNotes": notes_col.count_documents({}),
        "totalAssignments": assignments.count_documents({}),
        "totalPapers": papers_col.count_documents({}),
        "totalAnnouncements": announcements.count_documents({}),
        "totalTimetables": timetables.count_documents({}),
        "totalSyllabi": syllabi.count_documents({}),
        "totalCategories": categories.count_documents({}),
        "totalEvents": events_col.count_documents({}),
        "totalSubjects": subjects_col.count_documents({}),
        "totalSemesters": semesters_col.count_documents({}),
        "totalQuickLinks": quick_links_col.count_documents({}),
        "totalBanners": banners_col.count_documents({}),
        "totalNotifications": notifications_col.count_documents({}),
        "totalFeedback": feedback_col.count_documents({}),
        "storageUsed": total_size, "fileCount": file_count,
        "maxStorage": 100 * 1024 * 1024, "studentGrowth": growth_data,
    })




# ══════════════════════════════════════════════════════════════════════════════
#  FORUM (DISCUSSION BOARD)  /api/forum
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/forum")
def get_forum_posts():
    limit  = int(request.args.get("limit", 100))
    skip   = int(request.args.get("skip", 0))
    cursor = forum_col.find({}).sort("createdAt", DESCENDING).skip(skip).limit(limit)
    return jsonify([serialize(p) for p in cursor])

@app.post("/api/forum")
@auth_required
def create_forum_post():
    data = request.get_json(force=True)
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"msg": "Content is required"}), 400
    
    # Get user details
    user_id = request.user_id
    user_doc = users.find_one({"_id": ObjectId(user_id)})
    if not user_doc:
        return jsonify({"msg": "User not found"}), 404
        
    username = user_doc.get("username") or user_doc.get("fullName") or "Anonymous"
    email = user_doc.get("email") or ""
    
    post = {
        "content": content,
        "userId": user_id,
        "username": username,
        "email": email,
        "createdAt": datetime.datetime.utcnow()
    }
    
    forum_col.insert_one(post)
    return jsonify({"status": "ok", "post": serialize(post)})

@app.delete("/api/forum/<post_id>")
@auth_required
def delete_forum_post(post_id):
    if not is_admin(request.user_id):
        return jsonify({"msg": "Admin required"}), 403
        
    res = forum_col.delete_one({"_id": ObjectId(post_id)})
    if res.deleted_count == 0:
        return jsonify({"msg": "Post not found"}), 404
        
    log_admin_action("DELETE_FORUM_POST", f"Deleted post {post_id}")
    return jsonify({"status": "ok", "msg": "Post deleted successfully!"})


# ─── Error Handler ─────────────────────────────────────────────────────────────
@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    error_data = {
        "message": str(e), "traceback": traceback.format_exc(),
        "path": request.path, "method": request.method,
        "timestamp": datetime.datetime.utcnow()
    }
    try:
        error_logs.insert_one(error_data)
    except Exception:
        pass
    return jsonify({"msg": "An internal server error occurred"}), 500

# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Student Hub Backend v2.0  (Python Flask)")
    print(f"  http://localhost:{PORT}/api")
    print("=" * 55)
    app.run(host="0.0.0.0", port=PORT, debug=False)
