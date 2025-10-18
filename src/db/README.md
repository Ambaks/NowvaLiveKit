# Portable Database Module

A self-contained, reusable PostgreSQL database module for fitness/workout tracking applications. This module provides SQLAlchemy ORM models, Pydantic schemas, and database utilities that can be easily integrated into any Python project.

## Database Schema

This module includes the following tables:

- **users** - User accounts with authentication
- **program_templates** - Pre-defined workout program templates
- **programs** - User-created workout programs
- **workouts** - Individual workouts within programs
- **exercises** - Global catalog of exercises
- **workout_exercises** - Join table linking exercises to workouts
- **sets** - Set configurations (reps, weight, RPE)
- **progress_logs** - User workout performance tracking
- **schedule** - Workout scheduling

## Installation

### 1. Copy the Module

Copy the entire `portable_db_module` directory into your project:

```bash
cp -r portable_db_module /path/to/your/project/
```

### 2. Install Dependencies

```bash
cd /path/to/your/project
pip install -r portable_db_module/requirements.txt
```

Or install individually:
```bash
pip install sqlalchemy psycopg2-binary python-dotenv pydantic
```

### 3. Configure Database Connection

Create a `.env` file in your project root:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/your_database_name
```

Example:
```env
DATABASE_URL=postgresql://myuser:mypassword@localhost:5432/fitness_db
```

### 4. Initialize Database

Run the setup script to create all tables:

```bash
python portable_db_module/setup_db.py
```

Or initialize programmatically:

```python
from portable_db_module import init_db

init_db()
```

## Usage

### Basic Usage with SQLAlchemy

```python
from portable_db_module import SessionLocal, User, Program, Exercise

# Create a database session
db = SessionLocal()

# Query users
users = db.query(User).all()

# Create a new exercise
new_exercise = Exercise(
    name="Bench Press",
    category="Strength",
    muscle_group="Chest",
    description="Barbell bench press"
)
db.add(new_exercise)
db.commit()

# Close session
db.close()
```

### Usage with FastAPI

```python
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from portable_db_module import get_db, User, Program
from portable_db_module.schemas import UserRead, ProgramRead

app = FastAPI()

# Initialize database on startup
@app.on_event("startup")
async def startup():
    from portable_db_module import init_db
    init_db()

# Use dependency injection
@app.get("/users", response_model=list[UserRead])
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@app.get("/programs", response_model=list[ProgramRead])
def get_programs(db: Session = Depends(get_db)):
    return db.query(Program).all()
```

### Usage with Flask

```python
from flask import Flask, jsonify
from portable_db_module import SessionLocal, User, init_db

app = Flask(__name__)

# Initialize database
init_db()

@app.route('/users')
def get_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        return jsonify([{
            'id': str(user.id),
            'username': user.username,
            'email': user.email
        } for user in users])
    finally:
        db.close()

if __name__ == '__main__':
    app.run()
```

## Available Models

Import models directly from the module:

```python
from portable_db_module import (
    User,
    ProgramTemplate,
    Program,
    Workout,
    Exercise,
    WorkoutExercise,
    Set,
    ProgressLog,
    Schedule
)
```

## Available Schemas

For request/response validation with Pydantic:

```python
from portable_db_module.schemas import (
    UserCreate, UserRead,
    ProgramRead, ProgramBase,
    ExerciseRead, ExerciseBase,
    # ... and more
)
```

## Database Utilities

```python
from portable_db_module import engine, SessionLocal, get_db, init_db

# Initialize/create all tables
init_db()

# Get a database session
db = SessionLocal()

# Use with FastAPI dependency injection
from fastapi import Depends
def my_endpoint(db: Session = Depends(get_db)):
    # db is automatically provided and cleaned up
    pass
```

## Migration to New Project

To use this module in a new project:

1. Copy the `portable_db_module` folder to your new project
2. Install dependencies from `portable_db_module/requirements.txt`
3. Create a `.env` file with your `DATABASE_URL`
4. Run `python portable_db_module/setup_db.py` to create tables
5. Import and use the models in your application

## Environment Variables

- `DATABASE_URL` (required) - PostgreSQL connection string

Format: `postgresql://username:password@host:port/database_name`

## Example Database URLs

- Local: `postgresql://postgres:password@localhost:5432/mydb`
- Docker: `postgresql://postgres:password@db:5432/mydb`
- Cloud (Heroku): `postgresql://user:pass@ec2-xxx.compute.amazonaws.com:5432/dbname`
- Cloud (Railway): `postgresql://user:pass@containers-us-west-xxx.railway.app:5432/railway`

## Notes

- Uses PostgreSQL-specific UUID type for user IDs
- All timestamps use UTC (datetime.utcnow)
- Cascading deletes are configured for related records
- Indexes are created on foreign keys and email field
- Uses SQLAlchemy 2.0+ modern API

## Troubleshooting

### "DATABASE_URL environment variable is not set"
Make sure you have a `.env` file in your project root with the DATABASE_URL set.

### "could not connect to server"
Check that:
- PostgreSQL is running
- Host, port, username, and password are correct
- Database exists (create it if needed: `createdb your_database_name`)

### Import Errors
Ensure the module is in your Python path or install it as a package.
