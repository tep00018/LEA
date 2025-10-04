
```markdown
# 🚀 LEA Application Startup Guide

This document outlines the steps to start the **Learning Environment Architecture (LEA)** application locally and expose it via an `ngrok` tunnel for external access.

---

## 1️⃣ Activate LEA Environment
Ensure you have the correct Conda environment installed.

```bash
conda activate lea_clean
```

---

## 2️⃣ Start the Streamlit App
From the project root directory:

```bash
streamlit run src/ui/streamlit_app.py
```

By default, Streamlit will start on **http://localhost:8501**.

---

## 3️⃣ Create an `ngrok` Tunnel (Separate Terminal)
In a new terminal window:

```bash
ngrok http 8501
```

`ngrok` will provide a public URL (e.g., `https://<random>.ngrok.io`) that you can share for external access.

---

## 📌 Deployment Notes & Recommendations

When handing this off for deployment, consider including:

- **Environment Setup Instructions**
  - Conda installation link
  - Python version requirement
  - How to create the `lea_clean` environment from `environment.yml`:
    ```bash
    conda env create -f environment.yml
    ```

- **Secrets & Config**
  - Where to store API keys or credentials (e.g., `.env` file)
  - Example `.env.example` template

- **Port & Host Configuration**
  - How to change the default port if `8501` is in use:
    ```bash
    streamlit run src/ui/streamlit_app.py --server.port 8502
    ```

- **ngrok Setup**
  - Installation link: https://ngrok.com/download
  - How to authenticate with your ngrok account:
    ```bash
    ngrok config add-authtoken <YOUR_TOKEN>
    ```

- **Troubleshooting**
  - Common errors (e.g., Conda env not found, port already in use)
  - How to restart the app after code changes

- **Production Deployment Option**
  - Consider containerizing with Docker for consistent environments
  - Or hosting on Streamlit Cloud / Hugging Face Spaces for persistent access

---

## ✅ Quick Start Summary
```bash
conda activate lea_clean
streamlit run src/ui/streamlit_app.py
# In another terminal:
ngrok http 8501
```
