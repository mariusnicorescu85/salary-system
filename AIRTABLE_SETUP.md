# Airtable API Key Setup

To avoid entering your Airtable API key every time, you can set it up in one of three ways:

## Option 1: Environment Variable (Recommended for Local Development)

### Windows PowerShell:
```powershell
$env:AIRTABLE_API_KEY="your_api_key_here"
```

### Windows CMD:
```cmd
set AIRTABLE_API_KEY=your_api_key_here
```

### Linux/Mac:
```bash
export AIRTABLE_API_KEY="your_api_key_here"
```

**Note:** This only lasts for the current terminal session. To make it permanent:
- **Windows**: Add it to System Environment Variables
- **Linux/Mac**: Add `export AIRTABLE_API_KEY="your_key"` to your `~/.bashrc` or `~/.zshrc`

## Option 2: Streamlit Secrets (Recommended for Production)

1. Create a `.streamlit` folder in your project root (if it doesn't exist)
2. Create a file called `secrets.toml` inside `.streamlit/`
3. Add your API key:

```toml
[airtable]
api_key = "your_api_key_here"
```

**Note:** The `.streamlit/` folder is already in `.gitignore`, so your secrets won't be committed to git.

## Option 3: Session State (Temporary)

If you enter the API key once in the dashboard, it will be saved for the current session. However, you'll need to re-enter it if you restart Streamlit.

## Priority Order

The system checks for the API key in this order:
1. **Streamlit secrets** (`st.secrets.airtable.api_key`)
2. **Environment variable** (`AIRTABLE_API_KEY`)
3. **Session state** (saved from previous input in this session)
4. **Manual input** (if none of the above are found)

## Getting Your Airtable API Key / PAT Token

Airtable now uses **Personal Access Tokens (PAT)** instead of API keys:

1. Go to https://airtable.com/account
2. Scroll to the "Developer" section
3. Click "Create new token" or use an existing PAT token
4. Copy your PAT token (starts with `pat...`)
5. Keep it secure - don't share it publicly!

**Note:** PAT tokens work the same way as API keys in this system - just paste your token where it says "api_key".
