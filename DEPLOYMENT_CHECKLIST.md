# Streamlit Cloud Deployment Checklist

Use this checklist before deploying to ensure everything is ready.

## Pre-Deployment Checklist

### ✅ Code Preparation
- [ ] All code changes committed to git
- [ ] `app.py` is the main entry point
- [ ] `requirements.txt` includes all dependencies
- [ ] All config files in `config/` directory are committed
- [ ] `.streamlit/config.toml` is committed (optional but recommended)
- [ ] `.streamlit/secrets.toml` is NOT committed (should be in .gitignore)

### ✅ Repository Status
- [ ] Code pushed to GitHub
- [ ] Repository is public (or you have Streamlit Cloud Pro for private repos)
- [ ] Branch name is correct (usually `main` or `master`)

### ✅ Dependencies
- [ ] All Python packages listed in `requirements.txt`
- [ ] Package versions are compatible
- [ ] No local-only dependencies

### ✅ Configuration
- [ ] `config/shops.yaml` is configured
- [ ] Employee config files are present and configured
- [ ] All YAML files are valid

### ✅ Secrets Preparation
- [ ] Airtable API key ready (if using Airtable)
- [ ] Google Drive credentials (if using - note OAuth limitations)

## Deployment Steps

### Step 1: Deploy
- [ ] Go to [share.streamlit.io](https://share.streamlit.io)
- [ ] Sign in with GitHub
- [ ] Click "New app"
- [ ] Select repository
- [ ] Set main file: `app.py`
- [ ] Click "Deploy"
- [ ] Wait for deployment to complete

### Step 2: Configure Secrets
- [ ] Open app settings
- [ ] Go to "Secrets" tab
- [ ] Add Airtable API key in TOML format:
  ```toml
  [airtable]
  api_key = "your_key_here"
  ```
- [ ] Click "Save"
- [ ] App restarts automatically

### Step 3: Test
- [ ] App loads without errors
- [ ] Can select a shop
- [ ] Can upload a file
- [ ] Can run a calculation
- [ ] Results display correctly
- [ ] Airtable export works (if configured)

## Post-Deployment

### ✅ Verification
- [ ] App URL is accessible
- [ ] All features work as expected
- [ ] No errors in deployment logs
- [ ] Secrets are working

### ✅ Documentation
- [ ] Share app URL with team
- [ ] Document any special configuration needed
- [ ] Note any limitations (e.g., Google Drive OAuth)

## Common Issues & Quick Fixes

| Issue | Quick Fix |
|-------|-----------|
| Import errors | Check `requirements.txt` |
| Config not found | Verify `config/` is in git |
| Secrets not working | Check TOML format in secrets |
| App won't start | Check deployment logs |
| Slow performance | Normal for large files |

## Need Help?

- See `DEPLOY_STREAMLIT_CLOUD.md` for detailed instructions
- Check Streamlit Cloud logs in app dashboard
- Review `README.md` for app documentation
