# Deploy to Streamlit Cloud (Recommended)

## Prerequisites

1. **GitHub Account**: Your code must be in a GitHub repository
2. **Streamlit Account**: Sign up at [share.streamlit.io](https://share.streamlit.io) (free)
3. **Airtable API Key**: Get from [Airtable Account](https://airtable.com/account) (if using Airtable)

## Step-by-Step Deployment

### Step 1: Prepare Your Repository

1. **Ensure all files are committed**:
   ```bash
   git status
   git add .
   git commit -m "Ready for Streamlit Cloud deployment"
   ```

2. **Verify important files are present**:
   - ✅ `app.py` (main Streamlit app)
   - ✅ `requirements.txt` (dependencies)
   - ✅ `config/` directory with all YAML files
   - ✅ `.streamlit/config.toml` (optional, but recommended)

3. **Push to GitHub**:
   ```bash
   git push origin main
   ```
   (Replace `main` with your branch name if different)

### Step 2: Deploy on Streamlit Cloud

1. **Go to Streamlit Cloud**:
   - Visit [share.streamlit.io](https://share.streamlit.io)
   - Sign in with your GitHub account

2. **Create New App**:
   - Click **"New app"** button
   - Select your GitHub repository
   - Select the branch (usually `main` or `master`)
   - Set **Main file path**: `app.py`
   - (Optional) Set a custom app URL
   - Click **"Deploy"**

3. **Wait for deployment**:
   - Streamlit will automatically install dependencies from `requirements.txt`
   - First deployment may take 2-3 minutes
   - Watch the logs for any errors

### Step 3: Configure Secrets

1. **Open App Settings**:
   - In your app dashboard, click **"⋮"** (three dots) → **"Settings"**
   - Or go to: `https://share.streamlit.io/your-username/your-app-name/settings`

2. **Add Airtable API Key**:
   - Click on **"Secrets"** tab
   - Add the following in TOML format:
     ```toml
     [airtable]
     api_key = "your_airtable_api_key_here"
     ```
   - Replace `your_airtable_api_key_here` with your actual Airtable Personal Access Token
   - Click **"Save"**

3. **Verify Secrets**:
   - Your app will automatically restart after saving secrets
   - Check the logs to ensure no secret-related errors

### Step 4: Test Your Deployment

1. **Access your app**:
   - Your app URL will be: `https://your-app-name.streamlit.app`
   - Or: `https://share.streamlit.io/your-username/your-app-name`

2. **Test functionality**:
   - Upload a test file
   - Run a calculation
   - Verify Airtable export works (if configured)

## Important Notes

### ✅ What Works on Streamlit Cloud

- **File Uploads**: Users can upload CSV/Excel files directly - works perfectly!
- **Config Files**: All YAML configs in `config/` directory work as-is
- **Airtable Integration**: Works seamlessly with secrets configured
- **Session State**: All Streamlit features work normally

### ⚠️ Limitations & Considerations

- **Google Drive OAuth**: 
  - OAuth flow works but requires user authentication in browser
  - Token storage is per-session (users need to re-authenticate)
  - Consider using file uploads instead for better UX

- **File System**:
  - Files are read-only (except temporary uploads)
  - Monthly adjustments saved to `config/` will persist in git
  - Consider committing monthly adjustment files if needed

- **Secrets**:
  - Never commit API keys to git
  - Use Streamlit Cloud's secrets management
  - Secrets are encrypted and secure

### 🔒 Security Best Practices

1. **Never commit secrets**:
   - ✅ `.streamlit/secrets.toml` is in `.gitignore` (good!)
   - ✅ Use Streamlit Cloud secrets instead

2. **API Keys**:
   - Use Airtable Personal Access Tokens (PAT)
   - Rotate keys periodically
   - Use least-privilege access

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError` or import errors

**Solution**:
- Check `requirements.txt` includes all dependencies
- Verify package versions are compatible
- Check deployment logs for specific error messages

### Config Files Not Found

**Problem**: `FileNotFoundError` for config files

**Solution**:
- Ensure `config/` directory is committed to git
- Check file paths are relative (not absolute)
- Verify files exist in your GitHub repository

### Secrets Not Working

**Problem**: API key not found or authentication fails

**Solution**:
- Verify secret format is correct TOML:
  ```toml
  [airtable]
  api_key = "your_key"
  ```
- Check secret name matches code: `st.secrets.airtable.api_key`
- Ensure no extra spaces or quotes around the key
- Restart the app after saving secrets

### App Won't Deploy

**Problem**: Deployment fails or app won't start

**Solution**:
- Check deployment logs for errors
- Verify `app.py` has no syntax errors
- Ensure Python version is compatible (Streamlit Cloud uses Python 3.9+)
- Check `requirements.txt` for any incompatible packages

### Slow Performance

**Problem**: App is slow or times out

**Solution**:
- Large file uploads may take time - this is normal
- Consider optimizing data processing
- Check Streamlit Cloud resource limits (free tier has limits)

## Updating Your App

After making changes:

1. **Commit and push**:
   ```bash
   git add .
   git commit -m "Update description"
   git push origin main
   ```

2. **Streamlit Cloud auto-deploys**:
   - Changes are automatically detected
   - App redeploys within 1-2 minutes
   - Check deployment status in dashboard

## Advanced Configuration

### Custom Domain (Pro Feature)

If you have Streamlit Cloud Pro:
- Configure custom domain in app settings
- Add DNS records as instructed

### Environment Variables

You can also set environment variables in Streamlit Cloud:
- Go to Settings → Secrets
- Add as TOML format

### Multiple Environments

For staging/production:
- Create separate Streamlit Cloud apps
- Use different branches or repositories
- Configure different secrets per environment

## Support

- **Streamlit Cloud Docs**: [docs.streamlit.io/streamlit-cloud](https://docs.streamlit.io/streamlit-cloud)
- **Streamlit Community**: [discuss.streamlit.io](https://discuss.streamlit.io)
- **GitHub Issues**: Create an issue in your repository

## Quick Reference

**App URL Format**: `https://your-app-name.streamlit.app`

**Secrets Format**:
```toml
[airtable]
api_key = "pat..."
```

**Main File**: `app.py`

**Dependencies**: `requirements.txt`

**Config Files**: `config/*.yaml`
