import pymongo

# 1. Connect to MongoDB
# Using the same connection string as in app.py
MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME = 'tendering_db'

print(f"Connecting to MongoDB at: {MONGO_URI}")

try:
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    # Trigger a connection to check if server is up
    client.server_info() 
    
    db = client[DB_NAME]
    users_collection = db['user'] # MongoEngine by default uses snake_case class name as collection

    print(f"Connected to database: {DB_NAME}")
    
    # 2. Key Check
    # In SQLite we checked if file exists. In Mongo we check if collection exists or just count docs.
    user_count = users_collection.count_documents({})
    
    if user_count == 0:
        print("No users found! Please register a user first via the website.")
    else:
        print(f"\nFound {user_count} users:")
        print(f"{'USERNAME':<15} | {'SALT (Random Unique)':<35} | {'HASH (Result)'}")
        print("-" * 100)
        
        for user in users_collection.find():
            username = user.get('username', 'N/A')
            salt = user.get('password_salt', 'N/A')
            p_hash = user.get('password_hash', 'N/A')
            
            # Show first 20 chars of hash to keep it clean
            if len(p_hash) > 20: 
                p_hash = p_hash[:20] + "..."
            
            print(f"{username:<15} | {salt:<35} | {p_hash}")

except pymongo.errors.ServerSelectionTimeoutError:
    print("ERROR: Could not connect to MongoDB. Is it running?")
except Exception as e:
    print(f"Error reading database: {e}")