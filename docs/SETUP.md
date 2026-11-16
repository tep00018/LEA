# LEA Setup Guide

## System Requirements

### Minimum
- Python 3.11+
- 8GB RAM
- 10GB disk space
- Redis server

### Recommended
- Python 3.11+
- 16GB RAM
- 20GB disk space
- Redis 7.0+

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/tep00018/LEA.git
cd LEA
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Linux/Mac
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Install Redis

**macOS (Homebrew)**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis
```

**Windows**
```bash
# Use Docker
docker run -d -p 6379:6379 redis:latest
```

### 5. Configure Environment

```bash
cp .env.example .env
nano .env  # Edit with your credentials
```

Required:
```
OPENAI_API_KEY=sk-your-key-here
REDIS_URL=redis://localhost:6379
```

### 6. Run Application

```bash
# Verify Redis
redis-cli ping  # Should return "PONG"

# Start LEA
streamlit run src/ui/streamlit_app.py
```

Access at: http://localhost:8501

## Troubleshooting

### Redis Connection Error
```bash
redis-cli ping
# If fails, restart Redis
```

### Import Errors
```bash
pip install --force-reinstall -r requirements.txt
```

### ChromaDB Errors
```bash
rm -rf data/chroma_data/DEMO101/*
python data_foundation/rag_library_creation.py DEMO101
```

## Adding New Courses

See [Course Creation Guide](COURSE_CREATION.md) for instructions on adding additional courses to LEA.