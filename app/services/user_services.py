import os
import logging
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from app.utils.atlas_client import AtlasClient
from pydantic import EmailStr
from datetime import datetime
from bson.objectid import ObjectId
from app.services.clone_helper import clone_entry
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import base64


KEY_FILE = "key.bin"  # File to store the key securely

# Function to generate and store the AES key
def generate_and_store_key():
    if not os.path.exists(KEY_FILE):  # Generate only if not already stored
        key = os.urandom(32)  # 256-bit key
        with open(KEY_FILE, "wb") as f:
            f.write(key)  # Save the key securely
        print("🔑 AES Key generated and stored in 'key.bin'.")
    else:
        print("✅ AES Key already exists.")
        
# Function to load the stored key
def load_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()  # Read the stored key
    else:
        raise FileNotFoundError("❌ Key file not found! Generate it first.")

# Encrypt function
def encrypt(plaintext, key):
    iv = os.urandom(12)  # Generate a random IV (nonce)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    
    ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
    return base64.b64encode(iv + encryptor.tag + ciphertext).decode()  # Return as base64 string

# Decrypt function
def decrypt(encrypted_text, key):
    encrypted_data = base64.b64decode(encrypted_text)
    
    iv = encrypted_data[:12]   # Extract IV
    tag = encrypted_data[12:28]  # Extract GCM Tag
    ciphertext = encrypted_data[28:]  # Extract Ciphertext
    
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    
    return decryptor.update(ciphertext) + decryptor.finalize()

# List of valid project types
Project_Options = [
    "courses", "research_report", "create_a_video", "white_paper",
    "project_plan", "e_book", "create_a_podcast", "write_a_blog",
]

def _convert_object_ids_to_strings(data):
    if isinstance(data, dict):
        return {key: _convert_object_ids_to_strings(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_convert_object_ids_to_strings(item) for item in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data
    
# Email validation using Pydantic (or you can use regex here as well)
def validate_email(email: str) -> bool:
    try:
        EmailStr.validate(email)
        return True
    except ValueError:
        return False

# Date validation (assuming date format is 'YYYY-MM-DD')
def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")  # Check if date matches 'YYYY-MM-DD'
        return True
    except ValueError:
        return False

async def add_user_to_project_waitlist(user_id, user_email, project_id, project_name, date):
    atlas_client = AtlasClient()

    # Validate email format
    # if not validate_email(user_email):
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format.")
    
    # Validate date format
    if not validate_date(date):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Expected 'YYYY-MM-DD'.")
    
    # Ensure the project exists in the allowed project options
    if project_id not in Project_Options:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid project name. Valid options are: {', '.join(Project_Options)}"
        )
    
    # Check if the user has already signed up for the waitlist for the project
    user_project = atlas_client.find("project_waitlist", filter={"user_id": user_id, "project_id": project_id})
    
    if user_project:
        # If the user is already in the waitlist for this project, return a message
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "User is already on the waitlist for this project."}
        )
    
    # If not, add the user to the waitlist
    waitlist_entry = {
        "user_id": user_id,
        "user_email": user_email,
        "project_id": project_id,
        "project_name": project_name,
        "date": date,  # Date should already be validated
    }
    
    # Insert the new entry into the database
    try:
        atlas_client.insert("project_waitlist", waitlist_entry)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to insert waitlist entry: {str(e)}"
        )
    
    # Return a success response
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "User successfully added to the waitlist."}
    )
    
    atlas_client = AtlasClient()
    # Validate email format
    # if not validate_email(user_email):
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format.")
    
    # Validate date format
    if not validate_date(date):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Expected 'YYYY-MM-DD'.")
    
    # Ensure the project exists in the COURSE_DESIGN_STEPS
    if project_id not in Project_Options:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid project name. Valid options are: {', '.join(Project_Options)}")
    
    # Check if the user has already signed up for the waitlist for the project
    user_project = atlas_client.find("project_waitlist",  filter={"user_id": user_id, "project_id": project_id}  )
    
    if user_project:
        # If the user is already in the waitlist for this project, return a message
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "User is already on the waitlist for this project."}
        )
    
    # If not, add the user to the waitlist
    waitlist_entry = {
        "user_id": user_id,
        "user_email": user_email,
        "project_id": project_id,
        "project_name": project_name,
        "date": date,  # Date should already be validated
    }
    
    # Insert the new entry into the database
    atlas_client.find("project_waitlist").insert(waitlist_entry)
    
    # Return a success response
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "User successfully added to the waitlist."}
    )

async def fetch_notifications(username):
    atlas_client = AtlasClient()
    notifications = atlas_client.find("notifications", filter={"username": username})
    notifications = _convert_object_ids_to_strings(notifications)
    # Sort notifications by 'create_date' in descending order
    notifications.sort(key=lambda x: x['creation_date'], reverse=True)
    return notifications

async def toggle_notification_status(notification_list):
    notification_list = notification_list[0].split(',')
    atlas_client = AtlasClient()
    try:
        for notification_id in notification_list:
            # Use the `update` method to mark notification as read
            success = atlas_client.update(
                "notifications",
                filter={"_id": ObjectId(notification_id)},
                update={"$set": {"read": True}}
            )
            if not success:
                # Handle the case when the update failed (e.g., invalid ObjectId or no document found)
                raise Exception(f"Failed to update notification with ID: {notification_id}")
        return True
    except Exception as e:
        # Catch any exceptions and handle them
        logging.error(f"Error occurred: {e}")
        return False
    

async def register_user(username, email, firstName, lastName, phone):
    atlas_client = AtlasClient()
    # Check if the user already exists in the database
    user = atlas_client.find("qucreate_users", filter={"username": username})
    if user:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "User already exists."}
        )
    
    # If the user does not exist, insert a new user into the database
    user_entry = {
        "username": username,
        "email": email, 
        "first_name": firstName,
        "last_name": lastName,
        "phone": phone,
        "category": "user",
        "registration_date": datetime.now()
    }
    try:
        atlas_client.insert("qucreate_users", user_entry)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to insert user: {str(e)}"
        )

async def fetch_users():
    atlas_client = AtlasClient()
    users = atlas_client.find("qucreate_users")
    users = _convert_object_ids_to_strings(users)
    return users

async def clone_artifact(collection, id):
    cloned_entry = clone_entry(collection=collection, id=id)
    return cloned_entry

async def fetch_user(username):
    atlas_client = AtlasClient()
    user = atlas_client.find("qucreate_users", filter={"username": username})
    user = _convert_object_ids_to_strings(user)
    return user

async def fetch_quAPIVault(username):
    # Call this once to generate and store the key
    # generate_and_store_key()
     # Example Usage
    key = load_key()  # Securely generate a random key    
    atlas_client = AtlasClient()
    quAPIVault = atlas_client.find("quAPIVault", filter={"username": username})
    quAPIVault = _convert_object_ids_to_strings(quAPIVault)
    for entry in quAPIVault:
        if "key" in entry:
            decryptKey = decrypt(entry["key"], key)
            entry["key"] = decryptKey
    return quAPIVault

async def quAPIVault(username, company, model, key, name, description, type): 
    atlas_client = AtlasClient()
    
    # Check if the user exists in the database
    user = atlas_client.find("qucreate_users", filter={"username": username})
    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "User not found."}
        )

    private_key = load_key()  # Read the key
    encrypted = encrypt(key, private_key)  # Use the key for encryption

    key_id = ObjectId()

    # Insert the new API key into the database
    api_key_entry = {
        "_id": key_id,
        "username": username,
        "company": company,
        "model": model,
        "key": encrypted,
        "name": name,
        "description": description,
        "type": type
    }   

    try:
        atlas_client.insert("quAPIVault", api_key_entry)
        api_key_entry["key"] = key  # Return the original key
        api_key_entry = _convert_object_ids_to_strings(api_key_entry)  # Convert ObjectId to string
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "API key added successfully.",
                "response": api_key_entry
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to insert API key: {str(e)}"
        )

async def update_category(username, category):
    atlas_client = AtlasClient()
    # Check if the user exists in the database
    user = atlas_client.find("qucreate_users", filter={"username": username})
    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "User not found."}
        )
    
    # Update the user's category
    try:
        atlas_client.update(
            "qucreate_users",
            filter={"username": username},
            update={"$set": {"category": category}}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user category: {str(e)}"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "User category updated successfully."}
    )


async def edit_quAPIVault(key_id, model, name, description, key):
    atlas_client = AtlasClient()
    # Check if the API key exists in the database
    api_key_entry = atlas_client.find("quAPIVault", filter={"_id": ObjectId(key_id)})
    if not api_key_entry:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "API key not found."}
        )
    
    private_key = load_key()  # Read the key
    encrypted = encrypt(key, private_key)  # Use the key for
    
    # Update the API key
    try:
        atlas_client.update(
            "quAPIVault",
            filter={"_id": ObjectId(key_id)},
            update={"$set": {"key": encrypted, "name": name, "description": description, "model": model}}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update API key: {str(e)}"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "API key updated successfully."}
    )

async def delete_quAPIVault(key_id):
    atlas_client = AtlasClient()
    # Check if the API key exists in the database
    api_key_entry = atlas_client.find("quAPIVault", filter={"_id": ObjectId(key_id)})
    if not api_key_entry:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "API key not found."}
        )
    
    # Delete the API key
    try:
        atlas_client.delete("quAPIVault", filter={"_id": ObjectId(key_id)})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}"
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "API key deleted successfully."}
    )
