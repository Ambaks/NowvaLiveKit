# Quick Start Guide

## 5-Minute Setup

### Step 1: Copy to Your New Project
```bash
cp -r portable_db_module /path/to/your/new/project/
cd /path/to/your/new/project
```

### Step 2: Install Dependencies
```bash
pip install -r portable_db_module/requirements.txt
```

### Step 3: Configure Database
Create `.env` file:
```bash
echo "DATABASE_URL=postgresql://postgres:password@localhost:5432/mydb" > .env
```

### Step 4: Create Tables
```bash
python portable_db_module/setup_db.py
```

### Step 5: Use in Your Code
```python
from portable_db_module import SessionLocal, User, Exercise

db = SessionLocal()
users = db.query(User).all()
db.close()
```

## That's It!

For more details:
- See [README.md](README.md) for full documentation
- See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for detailed migration steps
- Run [example_usage.py](example_usage.py) to see working examples

## One-Liner Test
```bash
python portable_db_module/example_usage.py
```
