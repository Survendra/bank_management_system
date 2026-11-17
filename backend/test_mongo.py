import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

mongo_uri = os.getenv("MONGO_URI")

if not mongo_uri:
    raise RuntimeError("MONGO_URI is not configured in .env")

client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)

try:
    client.admin.command("ping")
    print("MongoDB Atlas connection successful!")

    db = client["bluebank"]
    print("Database:", db.name)

except Exception as error:
    print("MongoDB connection failed:")
    print(error)

finally:
    client.close()