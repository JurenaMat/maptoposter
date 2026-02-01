# MapToPoster Deployment Guide

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│   Cloudflare Pages  │     │  Google Cloud Run   │
│   (Static Frontend) │────▶│   (Python API)      │
│                     │     │                     │
│  - HTML/CSS/JS      │     │  - FastAPI          │
│  - Example images   │     │  - Map generation   │
│  - ~50KB-900KB      │     │  - Poster creation  │
└─────────────────────┘     └─────────────────────┘
            │                         │
            └────────┬────────────────┘
                     ▼
         ┌─────────────────────┐
         │   Cloudflare R2     │
         │   (Image Storage)   │
         │                     │
         │  - Generated posters│
         │  - CDN cached       │
         └─────────────────────┘
```

## Step 1: Deploy Backend to Google Cloud Run

### Prerequisites
- Google Cloud account with billing enabled
- `gcloud` CLI installed

### Commands

```bash
# Login to Google Cloud
gcloud auth login

# Create a new project (or use existing)
gcloud projects create maptoposter --name="MapToPoster"
gcloud config set project maptoposter

# Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com

# Build and deploy (from project root)
gcloud run deploy maptoposter-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --cpu 2

# Note the URL: https://maptoposter-api-xxxxx.run.app
```

### Environment Variables (set in Cloud Run)
- `R2_ACCOUNT_ID` - Cloudflare account ID
- `R2_ACCESS_KEY` - R2 access key
- `R2_SECRET_KEY` - R2 secret key
- `R2_BUCKET` - Bucket name (default: maptoposter)

## Step 2: Set Up Cloudflare R2 (Optional but recommended)

### Create R2 Bucket
1. Go to Cloudflare Dashboard → R2
2. Create bucket named `maptoposter`
3. Enable public access or set up custom domain
4. Create API token with R2 read/write permissions
5. Note the Account ID, Access Key, Secret Key

### Configure R2 in Cloud Run
```bash
gcloud run services update maptoposter-api \
  --set-env-vars "R2_ACCOUNT_ID=your_account_id" \
  --set-env-vars "R2_ACCESS_KEY=your_access_key" \
  --set-env-vars "R2_SECRET_KEY=your_secret_key" \
  --set-env-vars "R2_BUCKET=maptoposter"
```

## Step 3: Deploy Frontend to Cloudflare Pages

### Option A: Via Dashboard
1. Go to Cloudflare Dashboard → Pages
2. Create new project → Connect to Git
3. Select repository, set:
   - Build command: (leave empty)
   - Output directory: `frontend`
4. Add environment variable:
   - `MAPTOPOSTER_API_URL` = `https://your-cloud-run-url.run.app`

### Option B: Via Wrangler CLI
```bash
# Install wrangler
npm install -g wrangler

# Login
wrangler login

# Deploy
cd frontend
wrangler pages deploy . --project-name=maptoposter
```

### Update API URL in Frontend
Edit `frontend/index.html` and `frontend/generate.html`:
```javascript
window.MAPTOPOSTER_API_URL = 'https://maptoposter-api-xxxxx.run.app';
```

## Step 4: Configure Custom Domain (Optional)

### Cloudflare Pages
1. Go to Pages project → Custom domains
2. Add your domain (e.g., maptoposter.com)
3. Cloudflare handles SSL automatically

### Google Cloud Run
1. Go to Cloud Run → Service → Triggers
2. Add custom domain mapping
3. Configure DNS in Cloudflare

## Cost Estimates

| Service | Free Tier | Estimated Monthly |
|---------|-----------|-------------------|
| Cloudflare Pages | Unlimited | $0 |
| Cloudflare R2 | 10GB storage, 1M requests | $0-5 |
| Google Cloud Run | 2M requests/month | $0-20 |

## Monitoring

### Cloud Run
- View logs: `gcloud run logs read maptoposter-api`
- View metrics: Google Cloud Console → Cloud Run → Metrics

### Cloudflare
- Analytics: Pages dashboard
- R2: Storage usage in R2 dashboard

## Troubleshooting

### CORS Issues
The backend already has CORS configured for all origins. If you have issues:
1. Check Cloud Run logs for errors
2. Verify `allow_origins=["*"]` in app.py

### Slow Generation
- Increase Cloud Run memory: `--memory 4Gi`
- Increase timeout: `--timeout 600`

### Images Not Loading
1. Check R2 bucket permissions
2. Verify R2 environment variables in Cloud Run
3. Check browser console for 404 errors
