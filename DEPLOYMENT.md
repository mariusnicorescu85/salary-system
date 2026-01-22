# Deployment Guide

## ⚠️ Important: Vercel Limitation

**Vercel is NOT recommended for Streamlit apps** because:
- Vercel is designed for serverless functions and static sites
- Streamlit requires a persistent server process
- Vercel functions have execution time limits (10s on free tier, 60s on pro)
- Streamlit apps need long-running connections for WebSocket communication

## ✅ Recommended Hosting Options

### 1. **Streamlit Cloud** (Easiest & Free) ⭐ RECOMMENDED

**Best for:** Quick deployment, free tier available

**Steps:**
1. Push your code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Sign in with GitHub
4. Click "New app"
5. Select your repository and branch
6. Set main file to `app.py`
7. Add secrets in the dashboard:
   - `AIRTABLE_API_KEY`
   - Google Drive credentials (if needed)

**Pros:**
- Free tier available
- Automatic deployments from GitHub
- Built-in secrets management
- No server management

**Cons:**
- Limited to Streamlit apps
- Free tier has resource limits

---

### 2. **Railway** (Great for Python Apps)

**Best for:** Full control, easy setup

**Steps:**
1. Create account at [railway.app](https://railway.app)
2. Create new project from GitHub
3. Railway auto-detects Python
4. Add environment variables in dashboard
5. Deploy!

**Pros:**
- $5/month free credit
- Auto-deploys from GitHub
- Easy environment variable management
- Supports any Python app

**Cons:**
- Costs money after free credit
- Need to manage server resources

---

### 3. **Render** (Good Free Tier)

**Best for:** Free hosting with good features

**Steps:**
1. Create account at [render.com](https://render.com)
2. Create new "Web Service"
3. Connect GitHub repository
4. Set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
5. Add environment variables

**Pros:**
- Free tier available (with limitations)
- Auto-deploys from GitHub
- Easy setup

**Cons:**
- Free tier spins down after inactivity
- Slower cold starts

---

### 4. **Fly.io** (Good Performance)

**Best for:** Global distribution, good performance

**Steps:**
1. Install Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. Run `fly launch` in your project
3. Follow prompts
4. Add secrets: `fly secrets set AIRTABLE_API_KEY=your_key`

**Pros:**
- Good performance
- Global edge deployment
- Generous free tier

**Cons:**
- Requires CLI setup
- More complex than others

---

## 📋 Pre-Deployment Checklist

Before deploying, make sure:

- [ ] All secrets are configured (don't commit them!)
- [ ] `requirements.txt` is up to date
- [ ] Config files are ready
- [ ] Google Drive credentials are set up (if using)
- [ ] Airtable API key is available
- [ ] Test locally first!

---

## 🔐 Environment Variables Needed

Set these in your hosting platform:

```
AIRTABLE_API_KEY=your_key_here
```

For Google Drive (if using):
- Upload `credentials/google_drive_credentials.json` as a secret
- Or use environment variables for OAuth

---

## 📝 Files Needed for Deployment

The following files are already set up:
- ✅ `requirements.txt` - Dependencies
- ✅ `.gitignore` - Excludes credentials
- ✅ `config/` - Configuration files (commit these)

You may need to create:
- `Procfile` (for some platforms)
- `runtime.txt` (to specify Python version)
- `Dockerfile` (for containerized deployment)

See platform-specific files below.
