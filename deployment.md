# Deployment Guide

This guide covers how to deploy the AI-AGENT project from GitHub to Railway.

## Prerequisites
- A GitHub account.
- A Railway account (you can sign up using your GitHub account at [railway.app](https://railway.app)).
- The project pushed to your GitHub repository: [https://github.com/bsaiprasad13-main/AI-AGENT](https://github.com/bsaiprasad13-main/AI-AGENT).

## Step-by-Step Deployment to Railway

### 1. Push Your Code to GitHub
Ensure all your latest changes, including your `requirements.txt` and `Procfile`, are committed and pushed to your GitHub repository.

### 2. Create a New Project on Railway
1. Log in to [Railway](https://railway.app).
2. Click on **New Project** from your dashboard.
3. Select **Deploy from GitHub repo**.

### 3. Connect Your Repository
1. If this is your first time, you may need to grant Railway access to your GitHub repositories.
2. Select the repository: `bsaiprasad13-main/AI-AGENT`.

### 4. Configure Environment Variables
Before the app can run properly, you need to configure its environment variables based on `.env.example`.
1. Once the project is created, click on the **Variables** tab in your Railway project dashboard.
2. Add the following variables:
   - `ENVIRONMENT`: `production` (or `staging`)
   - `GEMINI_API_KEY`: Your actual Gemini API key.
   - `LLM_MODEL`: `gemini-1.5-pro` (or your preferred model)
   - `EMBEDDING_MODEL`: `sentence-transformers/all-MiniLM-L6-v2`
   - `MCP_SERVER_URL`: The URL of your MCP server
   - `API_KEY`: Your internal API key
   - `AUDIT_DB_PATH`: `data/audit.db`
   - `CACHE_DIR`: `data/cache`

> [!TIP]
> Railway has ephemeral storage by default. If your app writes data to `data/audit.db` or `data/cache`, that data will be lost on redeploys. To prevent this, go to **Settings > Volumes** in Railway and mount a volume to the `/app/data` path.

### 5. Build and Deploy
Railway uses Nixpacks to automatically build your project since it detects the `requirements.txt` file. 
It will use your `Procfile` (`web: python scripts/start_api.py`) to launch your application.

- The build process will start automatically once you link the repository.
- You can monitor the progress in the **Deployments** tab by clicking on the latest deployment to see the build logs.

### 6. Generate a Public Domain
1. Go to the **Settings** tab of your service.
2. Scroll down to the **Networking** section.
3. Click on **Generate Domain** to get a free `up.railway.app` URL (or you can link a custom domain). 
4. Once generated, your API will be accessible live at the provided URL!

## Troubleshooting

- **App Crashing on Boot**: Check the **Deployments** logs on Railway. Ensure that all necessary environment variables are set correctly, especially `GEMINI_API_KEY`.
- **Port Binding**: Railway expects your web server to listen on a dynamically assigned `PORT` environment variable, not a hardcoded one (like 8000). Ensure `scripts/start_api.py` uses this environment variable for Uvicorn:
  ```python
  import os
  import uvicorn
  
  if __name__ == "__main__":
      port = int(os.environ.get("PORT", 8000))
      uvicorn.run(app, host="0.0.0.0", port=port)
  ```
- **Missing Dependencies**: If you get `ModuleNotFoundError` during startup, make sure the missing package is added to your `requirements.txt` and pushed to GitHub.
