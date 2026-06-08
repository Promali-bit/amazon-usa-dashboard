# Amazon USA Finance & Product Dashboard

Password-protected Streamlit dashboard for matching Amazon reports:

- Business Report CSV
- Custom Unified Summary PDF

The dashboard displays finance KPIs, sales by ASIN, conversion, product charts,
reconciliation warnings, and an Excel summary download.

The PDF parser is designed for Amazon's current Custom Unified Summary format.
Users can review and correct the four headline statement figures in the sidebar
before downloading or relying on the summary.

## Deploy To Streamlit Community Cloud

1. Create a new GitHub repository, for example `amazon-usa-dashboard`.
2. Upload all files from this folder to the repository.
3. In Streamlit Community Cloud, deploy the repository using `app.py`.
4. Open the app's **Settings > Secrets** and add:

```toml
APP_PASSWORD = "use-a-long-private-password-here"
```

5. Save the secret and reboot the app if prompted.

Never commit `.streamlit/secrets.toml` or your real password to GitHub.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

Update `.streamlit/secrets.toml` with a local password before signing in.

## Security Notes

- Authentication uses a password stored in Streamlit secrets.
- Uploaded reports are processed in memory for the active session.
- The application does not intentionally write uploaded reports to disk.
- Anyone who knows the password can access the dashboard, so rotate it when needed.
- Streamlit's built-in authentication or a dedicated identity provider should be
  considered later if each user needs an individual account or access audit.
