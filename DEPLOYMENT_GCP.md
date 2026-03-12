# Deploying BrickSmart to GCP Cloud Run from GitHub

This guide walks you through deploying the BrickSmart Streamlit app to Google Cloud Platform using Cloud Run with continuous deployment from GitHub.

---

## Prerequisites

1. **Google Cloud Account** with billing enabled
2. **GitHub Repository** with your BrickSmart code
3. **gcloud CLI** installed (optional, for manual commands)

---

## Step-by-Step Deployment

### Step 1: Push Code to GitHub

First, ensure your code is pushed to a GitHub repository:

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit for GCP deployment"

# Add your GitHub remote
git remote add origin https://github.com/YOUR_USERNAME/BrickSmart.git

# Push to GitHub
git push -u origin main
```

**Important:** The `.gitignore` file excludes `.streamlit/secrets.toml` to prevent your API keys from being committed.

---

### Step 2: Create a GCP Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it `bricksmart` (or your preferred name)
4. Click **Create**

---

### Step 3: Enable Required APIs

In the Cloud Console, enable these APIs:

1. Go to **APIs & Services** → **Enable APIs and Services**
2. Search and enable:
   - **Cloud Run API**
   - **Cloud Build API**
   - **Secret Manager API**
   - **Artifact Registry API**

Or use gcloud CLI:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com
```

---

### Step 4: Store Your OpenAI Key in Secret Manager

1. Go to **Security** → **Secret Manager**
2. Click **Create Secret**
3. Name: `OPENAI_KEY`
4. Secret value: Your OpenAI API key (e.g., `sk-proj-...`)
5. Click **Create**

Or use gcloud CLI:

```bash
echo -n "sk-proj-YOUR_ACTUAL_KEY" | gcloud secrets create OPENAI_KEY --data-file=-
```

---

### Step 5: Set Up Cloud Run with GitHub Integration

#### Option A: Using Cloud Console (Recommended for First-Time Setup)

1. Go to **Cloud Run** in the Console
2. Click **Create Service**
3. Select **Continuously deploy from a repository**
4. Click **Set up with Cloud Build**
5. **Connect your GitHub repository:**
   - Authenticate with GitHub
   - Select your `BrickSmart` repository
   - Branch: `main` (or your default branch)
6. **Build Configuration:**
   - Build Type: **Dockerfile**
   - Source location: `/Dockerfile`
7. Click **Save**
8. **Configure the service:**
   - Service name: `bricksmart`
   - Region: Choose closest to your users (e.g., `us-central1`)
   - **CPU allocation:** CPU is always allocated (for Streamlit's websockets)
   - **Minimum instances:** 0 (or 1 for faster cold starts)
   - **Maximum instances:** 10
   - **Memory:** 1 GiB
   - **CPU:** 1
9. **Authentication:**
   - Select **Allow unauthenticated invocations** (for public access)
10. Click **Create**

#### Option B: Using gcloud CLI

```bash
# Deploy from source (builds and deploys)
gcloud run deploy bricksmart \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --port 8080
```

---

### Step 6: Configure Secrets for Cloud Run

After the service is created, you need to mount the secret:

1. Go to **Cloud Run** → Select your `bricksmart` service
2. Click **Edit & Deploy New Revision**
3. Go to the **Variables & Secrets** tab
4. Under **Secrets**, click **Reference a Secret**
5. Configure:
   - **Name:** `OPENAI_KEY`
   - **Secret:** Select `OPENAI_KEY` from dropdown
   - **Reference method:** **Exposed as environment variable**
   - **Environment variable name:** `OPENAI_KEY`
6. Click **Done** → **Deploy**

Or use gcloud CLI:

```bash
gcloud run services update bricksmart \
  --region us-central1 \
  --set-secrets=OPENAI_KEY=OPENAI_KEY:latest
```

---

### Step 7: Update Code to Read from Environment Variables

For the secrets to work, update the code to read from environment variables. I recommend this small change:

In `utils/utils.py`, the code already sets:
```python
os.environ['OPENAI_API_KEY'] = st.secrets['OPENAI_KEY']
```

For Cloud Run compatibility, update to support both:
```python
import os
openai_key = os.environ.get('OPENAI_KEY') or st.secrets.get('OPENAI_KEY')
os.environ['OPENAI_API_KEY'] = openai_key
```

---

### Step 8: Set Up Continuous Deployment (if not done in Step 5)

To enable automatic deployments when you push to GitHub:

1. Go to **Cloud Build** → **Triggers**
2. Click **Create Trigger**
3. Configure:
   - **Name:** `bricksmart-deploy`
   - **Event:** Push to a branch
   - **Source:** Select your GitHub repo
   - **Branch:** `^main$` (regex for main branch)
   - **Build Configuration:** Dockerfile
4. Click **Create**

---

## Accessing Your Deployed App

After deployment, Cloud Run provides a URL like:

```
https://bricksmart-XXXXXX-uc.a.run.app
```

Find it in:
- Cloud Run Console → Your service → URL at the top
- Or run: `gcloud run services describe bricksmart --region us-central1 --format='value(status.url)'`

---

## Estimated Costs

Cloud Run pricing (as of 2024):
- **Free tier:** 2 million requests/month, 360,000 GB-seconds of memory
- **Pay-per-use:** ~$0.00002400 per vCPU-second, ~$0.00000250 per GiB-second
- **Minimum instances:** If set to 0, you only pay when the app is used

For a low-traffic app, **costs should be minimal or free**.

---

## Troubleshooting

### View Logs

```bash
gcloud run logs read --service bricksmart --region us-central1
```

Or in Console: **Cloud Run** → **bricksmart** → **Logs**

### Common Issues

| Issue | Solution |
|-------|----------|
| Build fails | Check Dockerfile syntax and requirements-gcp.txt |
| Secret not found | Ensure secret exists and service account has access |
| App crashes on start | Check logs for Python errors |
| Cold start slow | Set minimum instances to 1 |

---

## Quick Reference Commands

```bash
# Deploy latest code
gcloud run deploy bricksmart --source . --region us-central1

# View logs
gcloud run logs read --service bricksmart --region us-central1

# Get service URL
gcloud run services describe bricksmart --region us-central1 --format='value(status.url)'

# Delete service (cleanup)
gcloud run services delete bricksmart --region us-central1
```

---

## Architecture Overview

```
┌──────────────┐     push      ┌──────────────┐
│   GitHub     │──────────────▶│ Cloud Build  │
│  Repository  │               │  (Trigger)   │
└──────────────┘               └──────┬───────┘
                                      │ build
                                      ▼
                               ┌──────────────┐
                               │  Artifact    │
                               │  Registry    │
                               └──────┬───────┘
                                      │ deploy
                                      ▼
┌──────────────┐               ┌──────────────┐
│   Secret     │◀──────────────│  Cloud Run   │
│   Manager    │   mount       │  (Service)   │
│  (OPENAI_KEY)│               └──────────────┘
└──────────────┘                      │
                                      ▼
                               ┌──────────────┐
                               │   Users      │
                               │   (HTTPS)    │
                               └──────────────┘
```
