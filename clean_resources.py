from openai import OpenAI
import os
from app.utils.atlas_client import AtlasClient
from bson.objectid import ObjectId

client = OpenAI(api_key=os.getenv("OPENAI_KEY"))


assistants = client.beta.assistants.list()
files = client.files.list()
vector_stores = client.beta.vector_stores.list()

print("Cleaning Assistants")
assistant_ids = [assistant.id for assistant in assistants]
for assistant_id in assistant_ids:
    print("Progress:", assistant_ids.index(assistant_id), "/", len(assistant_ids))
    try:
        client.beta.assistants.delete(assistant_id)
    except Exception:
        continue

print("Cleaning Files")
file_ids = [file.id for file in files]
for file_id in file_ids:
    print("Progress:", file_ids.index(file_id), "/", len(file_ids))
    try:
        client.files.delete(file_id)
    except Exception:
        continue

