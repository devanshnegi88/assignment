# Render Deployment Guide

## Prerequisites
- GitHub account with this repository
- Render.com account (free tier available)

## Deployment Steps

### 1. Push to GitHub
```bash
git add .
git commit -m "Prepare for Render deployment"
git push origin main
```

### 2. Create Render Account
1. Go to https://render.com
2. Sign up with GitHub
3. Authorize Render to access your repositories

### 3. Deploy via render.yaml
1. Go to https://dashboard.render.com/
2. Click "New +" → "Blueprint"
3. Select your GitHub repository
4. Select branch: `main`
5. Render will automatically detect `render.yaml` and deploy both services

### 4. Environment Variables (Optional)
To enable Gemini-based features on Render, add environment variables to the backend service:

1. Go to backend service → Environment
2. Add:
   - `LLM_PROVIDER`: "gemini"
   - `LLM_API_KEY`: your Gemini API key
   - `LLM_MODEL`: "gemini-1.5-flash" (default)

**Note**: The app works perfectly with `LLM_PROVIDER=template` (default) which requires NO API keys.

### 5. Access Your Deployment
- **Frontend**: https://shl-recommender-frontend.onrender.com
- **Backend API**: https://shl-recommender-backend.onrender.com
- **API Docs**: https://shl-recommender-backend.onrender.com/docs

### 6. Monitor Deployment
1. Go to https://dashboard.render.com/
2. Click on each service to view logs
3. Both services must show "Live" status

## Architecture

- **Backend**: FastAPI service on port 8000 (auto-selected by Render)
  - Hybrid retrieval: BM25 + sentence-transformers
  - Deterministic conversation management
  - Optional Gemini LLM integration
  - Falls back to template LLM if Gemini unavailable

- **Frontend**: React + TypeScript served by Node
  - Connects to backend via VITE_API_BASE_URL
  - Fully responsive UI
  - Real-time conversation interface

## Free Tier Limitations

- Services spin down after 15 min of inactivity (first request will be slow)
- 0.5GB RAM per service
- 400 hours/month combined

For production, upgrade to Starter plan ($7/month per service).

## Troubleshooting

### "Build failed"
- Check backend/requirements.txt for conflicting versions
- Ensure Dockerfile references correct paths
- Check build logs in Render dashboard

### "Service unavailable"
- Wait 2-3 minutes for service to start
- Check if service is in "Deploy in progress" state
- Restart service from dashboard

### "CORS errors"
- Backend allows all origins by default (`ALLOWED_CORS_ORIGINS=*`)
- If needed, set `ALLOWED_CORS_ORIGINS` to specific domain

### "Empty recommendations"
- Normal for first request (model files downloading)
- Subsequent requests will have cached embeddings
- Check backend logs: `tail -f /var/log/shl-recommender-backend.log`

## Customization

To change deployment names:
1. Edit `render.yaml` service names
2. Update frontend `VITE_API_BASE_URL` if backend name changes
3. Commit and push
4. Render auto-detects changes and re-deploys

## Local Testing Before Deploy
```bash
# Build Docker images locally
docker-compose up

# Test backend
curl http://localhost:8000/health

# Test frontend
open http://localhost:5173
```

## Support
- Render Docs: https://render.com/docs
- Backend API: https://fastapi.tiangolo.com/
- Frontend: React + TypeScript + Vite
