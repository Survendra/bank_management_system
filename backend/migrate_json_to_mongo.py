import json
import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
JSON_FILE = os.path.join(os.path.dirname(__file__), "bank_data.json")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not configured in .env")

client = MongoClient(MONGO_URI)

try:
    db = client["bluebank"]
    accounts_collection = db["accounts"]

    with open(JSON_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    accounts = data.get("accounts", {})

    if not isinstance(accounts, dict):
        raise ValueError("Invalid accounts structure in bank_data.json")

    inserted = 0
    updated = 0

    for account_number, account in accounts.items():
        account["account_number"] = account_number

        result = accounts_collection.update_one(
            {"account_number": account_number},
            {"$set": account},
            upsert=True,
        )

        if result.upserted_id:
            inserted += 1
        else:
            updated += 1

    print("Migration successful!")
    print(f"Inserted accounts: {inserted}")
    print(f"Updated accounts: {updated}")
    print(f"Total accounts in JSON: {len(accounts)}")

    print("\nAccounts in MongoDB:")
    for account in accounts_collection.find(
        {},
        {"_id": 0, "account_number": 1, "name": 1, "balance": 1},
    ):
        print(account)

finally:
    client.close()