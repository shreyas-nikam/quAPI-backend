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
OPENAI_KEY=<YOUR_KEY_HERE>
OPENAI_MODEL=<YOUR_KEY_HERE>
COHERE_API_KEY=<YOUR_KEY_HERE>
AWS_ACCESS_KEY=<YOUR_KEY_HERE>
AWS_SECRET_KEY=<YOUR_KEY_HERE>
AWS_BUCKET_NAME=<YOUR_KEY_HERE>
GEMINI_API_KEY=<YOUR_KEY_HERE>
ATLAS_URI=<YOUR_KEY_HERE>
LINKEDIN_CLIENT_ID=<YOUR_KEY_HERE>
LINKEDIN_CLIENT_SECRET=<YOUR_KEY_HERE>
COHERE_API_KEY=<YOUR_KEY_HERE>
TAVILY_API_KEY=<YOUR_KEY_HERE>
AZURE_TTS_SERVICE_REGION=<YOUR_KEY_HERE>
AZURE_TTS_SPEECH_KEY=<YOUR_KEY_HERE>
DOCUMENT_INTELLIGENCE_ENDPOINT <YOUR_KEY_HERE>
DOCUMENT_INTELLIGENCE_KEY <YOUR_KEY_HERE>

5. Launch backend:
   ```
   uvicorn app.main:app --reload
   ```

