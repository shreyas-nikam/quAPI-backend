# FastAPI Backend

A FastAPI application setup with proper environment configuration and a basic route.

## Setup

1. Clone the repository and navigate to the directory.
2. Create a virtual environment and activate it.
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use venv\Scripts\activate
   ```
3. Install requirements:
   ```
   pip install -r requirements.txt
   ```
4. Start a docker container for redis for notification streaming:
```
docker run --name local-redis -p 6379:6379 -d redis
```


4. Create .env file and add the following keys:
```
OPENAI_KEY=
OPENAI_MODEL=
AWS_ACCESS_KEY=
AWS_SECRET_KEY=
AWS_BUCKET_NAME=
GEMINI_API_KEY=
GEMINI_MODEL=
ATLAS_URI=
DB_NAME=
GITHUB_USERNAME=
GITHUB_TOKEN=
```

5. Launch backend:
   ```
   uvicorn app.main:app --reload
   ```
## For deployment:

1. Run `pm2 start "gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8001 --timeout 600" --name backend`  

2. Update the nginx file (You can navigate to the nginx file or create a new one: `cd /etc/nginx/sites-available/qucoursify`):
```

location /qucoursify {
                rewrite ^/qucoursify/(.*)$ /$1 break;     
                proxy_pass http://localhost:3001;
                proxy_http_version 1.1;
                proxy_set_header Upgrade $http_upgrade;
                proxy_set_header Connection 'upgrade';
                proxy_set_header Host $host;
                proxy_set_header Origin '';
                proxy_cache_bypass $http_upgrade;
   
}
```

3. Restart the nginx (Optional)
```
sudo systemctl reload nginx
```

4. Check if the endpoint is working by typing in quskillbridge.qusandbox.com/qucoursifyapi in the browser. It should return {"message":"Hello, World!"}

5. Check the logs by running the following command
```
pm2 logs backend
```


