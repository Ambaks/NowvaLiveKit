# Migration Guide

## Quick Start: Moving to a New Project

Follow these steps to integrate this database module into your new project:

### 1. Copy the Module

```bash
# From your current project directory
cp -r portable_db_module /path/to/new/project/
```

### 2. Install Dependencies

In your new project:

```bash
cd /path/to/new/project
pip install -r portable_db_module/requirements.txt
```

### 3. Configure Environment

Create a `.env` file in your new project root:

```bash
# Copy the example
cp portable_db_module/.env.example .env

# Edit with your database credentials
nano .env  # or use your preferred editor
```

Update the `DATABASE_URL`:
```
DATABASE_URL=postgresql://your_user:your_password@localhost:5432/your_new_db
```

### 4. Create Database

Make sure your PostgreSQL database exists:

```bash
# Using psql
createdb your_new_db

# Or connect to PostgreSQL and run:
CREATE DATABASE your_new_db;
```

### 5. Initialize Tables

```bash
python portable_db_module/setup_db.py
```

### 6. Start Using in Your Code

```python
from portable_db_module import SessionLocal, User, Exercise

# Create a session
db = SessionLocal()

# Query data
users = db.query(User).all()

# Close session
db.close()
```

## Framework-Specific Integration

### FastAPI

```python
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from portable_db_module import get_db, User, init_db

app = FastAPI()

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

### Flask

```python
from flask import Flask
from portable_db_module import SessionLocal, init_db

app = Flask(__name__)

# Initialize on startup
init_db()

@app.route('/users')
def get_users():
    db = SessionLocal()
    try:
        return [u.username for u in db.query(User).all()]
    finally:
        db.close()
```

### Django

While this is a SQLAlchemy module (not Django ORM), you can still use it:

```python
# In your Django views/services
from portable_db_module import SessionLocal, User

def some_view(request):
    db = SessionLocal()
    try:
        users = db.query(User).all()
        # Process users...
    finally:
        db.close()
```

## Sharing Database Between Projects

If you have multiple projects using the same database:

1. Each project gets its own copy of `portable_db_module`
2. All projects point to the same `DATABASE_URL`
3. Run `setup_db.py` only once (tables are shared)
4. All projects can read/write to the same database

Example `.env` for both projects:
```
# Project A and Project B both use:
DATABASE_URL=postgresql://user:pass@localhost:5432/shared_fitness_db
```

## Migration Checklist

- [ ] Copy `portable_db_module` folder to new project
- [ ] Install dependencies from `requirements.txt`
- [ ] Create `.env` file with `DATABASE_URL`
- [ ] Create PostgreSQL database if it doesn't exist
- [ ] Run `python portable_db_module/setup_db.py`
- [ ] Test connection with `example_usage.py`
- [ ] Import models in your application code
- [ ] Start building!

## Troubleshooting

### Problem: "No module named 'portable_db_module'"

**Solution:** Make sure the module is in your project directory or Python path.

```python
# If needed, add to path
import sys
sys.path.insert(0, '/path/to/portable_db_module')
```

### Problem: "DATABASE_URL environment variable is not set"

**Solution:** Create a `.env` file in your project root with DATABASE_URL.

### Problem: "relation 'users' does not exist"

**Solution:** Run the setup script to create tables:
```bash
python portable_db_module/setup_db.py
```

### Problem: Tables already exist in shared database

**Solution:** That's fine! SQLAlchemy will use existing tables. Just make sure you don't run migrations that might alter the schema if other projects depend on it.

## Best Practices

1. **Version Control:** Add `portable_db_module/` to your git repo
2. **Don't Commit .env:** Add `.env` to `.gitignore`
3. **Document Changes:** If you modify models, update all projects using this module
4. **Backup Data:** Before running setup in production, backup your database
5. **Use Migrations:** For production, consider using Alembic for schema migrations

## Next Steps

- Review [README.md](README.md) for detailed usage
- Check [example_usage.py](example_usage.py) for code examples
- Consider setting up Alembic for database migrations
- Add custom CRUD functions as needed for your use case
