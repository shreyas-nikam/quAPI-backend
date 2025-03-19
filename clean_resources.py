import requests

from openai import OpenAI
import os
from app.utils.atlas_client import AtlasClient
from bson.objectid import ObjectId
import logging
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(timeout=120, api_key=os.getenv("OPENAI_KEY"))


assistants = client.beta.assistants.list()
files = client.files.list()
vector_stores = client.vector_stores.list()

logging.info("Cleaning Assistants")
assistant_ids = [assistant.id for assistant in assistants]
for assistant_id in assistant_ids:
    logging.info("Progress:", assistant_ids.index(assistant_id), "/", len(assistant_ids))
    try:
        client.beta.assistants.delete(assistant_id)
    except Exception:
        continue

logging.info("Cleaning Files")
file_ids = [file.id for file in files]
for file_id in file_ids:
    logging.info("Progress:", file_ids.index(file_id), "/", len(file_ids))
    try:
        client.files.delete(file_id)
    except Exception:
        continue

# GitHub API URL and Token
GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")  

# list all the repositories
def list_repos():
    url = f"{GITHUB_API_URL}/users/{GITHUB_USERNAME}/repos?page=2"
    params = {
        "per_page": 100,   # MAX limit per request is 100
        "page": 1,         # Start from page 1
    }
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }

    all_repos = []

    while url:
        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 200:
            repos = response.json()
            if not repos:  # Stop if no more repos
                break
            all_repos.extend(repos)

            # Check if there's a "next" page in the Link header
            next_page = response.links.get("next", {}).get("url")
            url = next_page  # Update URL to fetch the next page
            params = {}  # Clear params, as next_page already has them in the URL

        else:
            print(f"Error: {response.status_code} - {response.text}")
            break

    return all_repos

    
# get all the current labs from labs_design collection from mongodb test and production collection
def get_labs():
    labs = []
    client = AtlasClient(dbname="test")
    for lab in client.find("lab_design", {}):
        labs.append(lab)
    client = AtlasClient(dbname="production")
    for lab in client.find("lab_design", {}):
        labs.append(lab)
    return labs

# delete all the repositories from github which are not in labs_design collection
def clean_repos():
    repos = list_repos()
    print(len(repos))
    print("Repositories:", [repo["name"] for repo in repos])
    labs = get_labs()
    print("Labs:", [str(lab["_id"]) for lab in labs])
    lab_names = set([str(lab["_id"]) for lab in labs])
    for repo in repos[:]:
        if repo["name"].startswith("67") and repo["name"] not in lab_names:
            print(f"Deleting repository: {repo['name']} with description: \n{repo['description']}\n\n")
            confirmation = input("Are you sure you want to delete this repository? (y/n): ")
            if confirmation.lower() != "y":
                continue
            url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo['name']}"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
            }
            response = requests.delete(url, headers=headers)
            if response.status_code == 204:
                logging.info(f"Repository '{repo['name']}' deleted successfully!")
            else:
                logging.info(f"Failed to delete repository: {response.status_code}, {response.text}")

clean_repos()