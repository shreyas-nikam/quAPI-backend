from fastapi import FastAPI, HTTPException, Request, Depends
from pydantic import BaseModel
from bson import ObjectId
from dotenv import load_dotenv
import os
import bcrypt
import jwt
from app.utils.atlas_client import AtlasClient  # Assuming the provided AtlasClient is saved in atlas_client.py

# Load environment variables
load_dotenv()

# JWT Secret
JWT_SECRET = os.getenv("JWT_SECRET")

# Initialize AtlasClient
atlas_client = AtlasClient()

# FastAPI app
app = FastAPI()

# Models
class SignUpModel(BaseModel):
    username: str
    password: str
    attributes: dict

class SignInModel(BaseModel):
    username: str
    password: str

class UpdateAttributesModel(BaseModel):
    username: str
    attributes: dict

class ForgotPasswordModel(BaseModel):
    username: str
    resetCode: str
    newPassword: str

class ConfirmSignUpModel(BaseModel):
    username: str
    confirmationCode: str

# Helper functions
def generate_token(data):
    return jwt.encode(data, JWT_SECRET, algorithm="HS256")

def verify_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# API Endpoints
@app.post("/signup")
def sign_up(data: SignUpModel):
    existing_user = atlas_client.find("users", {"username": data.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed_password = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt())
    new_user = {
        "username": data.username,
        "password": hashed_password,
        "attributes": data.attributes,
        "confirmed": False,
    }

    atlas_client.insert("users", new_user)

    token = generate_token({"username": data.username, "attributes": data.attributes})
    return {"token": token, "user": {"username": data.username, "attributes": data.attributes}}

@app.post("/confirm-signup")
def confirm_sign_up(data: ConfirmSignUpModel):
    user = atlas_client.find("users", {"username": data.username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.confirmationCode == "123456":  # Replace with actual confirmation logic
        atlas_client.update("users", {"username": data.username}, {"$set": {"confirmed": True}})
        return {"status": "SUCCESS"}
    else:
        raise HTTPException(status_code=400, detail="Invalid confirmation code")

@app.post("/signin")
def sign_in(data: SignInModel):
    user = atlas_client.find("users", {"username": data.username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user[0]["confirmed"]:
        raise HTTPException(status_code=400, detail="User not confirmed")

    if not bcrypt.checkpw(data.password.encode("utf-8"), user[0]["password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    token = generate_token({"username": user[0]["username"], "attributes": user[0]["attributes"]})
    return {"token": token, "user": {"username": user[0]["username"], "attributes": user[0]["attributes"]}}

@app.get("/current-authenticated-user")
def current_authenticated_user(request: Request):
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = token.split("Bearer ")[-1]
    decoded = verify_token(token)

    user = {
        "username": decoded["username"],
        "attributes": decoded["attributes"],
        "signInUserSession": {
            "accessToken": {
                "payload": {"cognito:groups": decoded.get("groups", ["member"])}
            }
        },
    }
    return user

@app.post("/signout")
def sign_out():
    return {"status": "SUCCESS"}

@app.post("/forgot-password")
def forgot_password(username: str):
    user = atlas_client.find("users", {"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"resetCode": "123456"}  # Replace with actual reset logic

@app.post("/forgot-password-submit")
def forgot_password_submit(data: ForgotPasswordModel):
    user = atlas_client.find("users", {"username": data.username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.resetCode == "123456":  # Replace with actual reset code logic
        hashed_password = bcrypt.hashpw(data.newPassword.encode("utf-8"), bcrypt.gensalt())
        atlas_client.update("users", {"username": data.username}, {"$set": {"password": hashed_password}})
        return {"status": "SUCCESS"}
    else:
        raise HTTPException(status_code=400, detail="Invalid reset code")

@app.post("/update-user-attributes")
def update_user_attributes(data: UpdateAttributesModel):
    result = atlas_client.update("users", {"username": data.username}, {"$set": {"attributes": data.attributes}})
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "SUCCESS"}
