from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/student_hub")

client = MongoClient(MONGO_URI)
db = client.get_database()
users = db["users"]

print("USERS:")
for u in users.find({}, {"password": 0}):
    print(u)
