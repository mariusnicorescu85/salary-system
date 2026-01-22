# Repository Cleanup Guide

This guide helps you keep only essential files in your repository for Streamlit Cloud deployment.

## Files Needed for Deployment

### ✅ Essential Files (MUST keep)
- `app.py` - Main Streamlit application
- `requirements.txt` - Python dependencies
- `src/` - All Python modules (calculation_engine.py, data_processor.py, etc.)
- `config/` - All YAML configuration files
- `.streamlit/config.toml` - Streamlit configuration
- `.gitignore` - Git ignore rules
- `README.md` - Project documentation (recommended)

### ✅ Optional but Useful
- `DEPLOY_STREAMLIT_CLOUD.md` - Deployment guide (helpful for future reference)

### ❌ Not Needed (can be removed)
- `report.csv` - Test data file
- `Dockerfile` - Not used by Streamlit Cloud
- `Procfile` - Not used by Streamlit Cloud
- `runtime.txt` - Not used by Streamlit Cloud
- Documentation files (except README.md and DEPLOY_STREAMLIT_CLOUD.md):
  - `AIRTABLE_DATA_RETRIEVAL.md`
  - `AIRTABLE_SETUP.md`
  - `EMAIL_AND_AIRTABLE_SETUP.md`
  - `EMAIL_BREAKDOWN_PREVIEW.md`
  - `LOCAL_TESTING.md`
  - `MONTHLY_ADJUSTMENTS_GUIDE.md`
  - `QUICKSTART.md`
  - `UPDATES.md`
  - `VERCEL_WARNING.md`
  - `DEPLOYMENT.md`
  - `DEPLOYMENT_CHECKLIST.md`

## How to Clean Up Your Repository

### Option 1: Remove Files from Git (Keep Locally)

If you want to remove files from git but keep them on your local machine:

```bash
# Remove specific files from git tracking (but keep locally)
git rm --cached report.csv
git rm --cached Dockerfile
git rm --cached Procfile
git rm --cached runtime.txt
git rm --cached AIRTABLE_DATA_RETRIEVAL.md
git rm --cached AIRTABLE_SETUP.md
git rm --cached EMAIL_AND_AIRTABLE_SETUP.md
git rm --cached EMAIL_BREAKDOWN_PREVIEW.md
git rm --cached LOCAL_TESTING.md
git rm --cached MONTHLY_ADJUSTMENTS_GUIDE.md
git rm --cached QUICKSTART.md
git rm --cached UPDATES.md
git rm --cached VERCEL_WARNING.md
git rm --cached DEPLOYMENT.md
git rm --cached DEPLOYMENT_CHECKLIST.md

# Commit the changes
git commit -m "Remove unnecessary files from repository"

# Push to GitHub
git push origin main
```

### Option 2: Remove Files Completely

If you want to delete the files entirely:

```bash
# Delete files locally and from git
git rm report.csv
git rm Dockerfile
git rm Procfile
git rm runtime.txt
git rm AIRTABLE_DATA_RETRIEVAL.md
git rm AIRTABLE_SETUP.md
git rm EMAIL_AND_AIRTABLE_SETUP.md
git rm EMAIL_BREAKDOWN_PREVIEW.md
git rm LOCAL_TESTING.md
git rm MONTHLY_ADJUSTMENTS_GUIDE.md
git rm QUICKSTART.md
git rm UPDATES.md
git rm VERCEL_WARNING.md
git rm DEPLOYMENT.md
git rm DEPLOYMENT_CHECKLIST.md

# Commit the changes
git commit -m "Remove unnecessary files from repository"

# Push to GitHub
git push origin main
```

### Option 3: Use .gitignore (Recommended)

The `.gitignore` file has been updated to automatically exclude these files. However, files already committed will still be tracked. Use Option 1 or 2 first, then future files will be automatically ignored.

## Verify Your Repository

After cleanup, your repository should have:

```
salary_calculation_system/
├── .gitignore
├── .streamlit/
│   └── config.toml
├── app.py
├── requirements.txt
├── README.md
├── DEPLOY_STREAMLIT_CLOUD.md (optional)
├── config/
│   ├── shops.yaml
│   ├── employees_pyt.yaml
│   ├── employees_silverburn.yaml
│   ├── employees_opatra.yaml
│   └── monthly_adjustments_*.yaml
└── src/
    ├── calculation_engine.py
    ├── data_processor.py
    ├── google_drive_client.py
    ├── airtable_client.py
    └── email_client.py
```

## After Cleanup

1. **Verify Streamlit Cloud still works**:
   - Your app should automatically redeploy
   - Check the deployment logs for any errors

2. **Test the app**:
   - Visit your Streamlit Cloud URL
   - Test file upload
   - Test calculations
   - Verify everything works

## Notes

- Files in `.gitignore` won't be committed in the future
- You can always add files back if needed
- Documentation files can be kept locally for reference
- The app will work fine with or without these files
