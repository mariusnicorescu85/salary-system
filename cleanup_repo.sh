#!/bin/bash
# Cleanup script for Linux/Mac - removes unnecessary files from git tracking
# This keeps files locally but removes them from git

echo "Removing unnecessary files from git tracking..."
echo

git rm --cached report.csv 2>/dev/null
git rm --cached Dockerfile 2>/dev/null
git rm --cached Procfile 2>/dev/null
git rm --cached runtime.txt 2>/dev/null
git rm --cached AIRTABLE_DATA_RETRIEVAL.md 2>/dev/null
git rm --cached AIRTABLE_SETUP.md 2>/dev/null
git rm --cached EMAIL_AND_AIRTABLE_SETUP.md 2>/dev/null
git rm --cached EMAIL_BREAKDOWN_PREVIEW.md 2>/dev/null
git rm --cached LOCAL_TESTING.md 2>/dev/null
git rm --cached MONTHLY_ADJUSTMENTS_GUIDE.md 2>/dev/null
git rm --cached QUICKSTART.md 2>/dev/null
git rm --cached UPDATES.md 2>/dev/null
git rm --cached VERCEL_WARNING.md 2>/dev/null
git rm --cached DEPLOYMENT.md 2>/dev/null
git rm --cached DEPLOYMENT_CHECKLIST.md 2>/dev/null

echo
echo "Files removed from git tracking (but kept locally)."
echo
echo "Next steps:"
echo "1. Review changes: git status"
echo "2. Commit: git commit -m 'Remove unnecessary files from repository'"
echo "3. Push: git push origin main"
