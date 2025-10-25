#!/bin/bash
# Get or create a test user in the database

echo "=================================="
echo "Get or Create Test User"
echo "=================================="
echo ""

# Load DATABASE_URL from .env if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep DATABASE_URL | xargs)
fi

if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL not set in environment or .env file"
    echo ""
    echo "Please set DATABASE_URL in your .env file:"
    echo "  DATABASE_URL=postgresql://user:password@localhost:5432/dbname"
    exit 1
fi

echo "Database: $DATABASE_URL"
echo ""

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "❌ psql command not found"
    echo ""
    echo "Install PostgreSQL client:"
    echo "  brew install postgresql"
    exit 1
fi

# Try to get an existing user
echo "Looking for existing users..."
EXISTING_USER=$(psql "$DATABASE_URL" -t -c "SELECT id FROM users LIMIT 1;" 2>/dev/null | tr -d ' ')

if [ -n "$EXISTING_USER" ]; then
    echo "✅ Found existing user:"
    echo ""
    psql "$DATABASE_URL" -c "SELECT id, name, email, created_at FROM users LIMIT 5;"
    echo ""

    # Get first user ID
    FIRST_USER_ID=$(psql "$DATABASE_URL" -t -c "SELECT id FROM users LIMIT 1;" | tr -d ' ')

    echo ""
    echo "📋 Use this User ID for testing:"
    echo "$FIRST_USER_ID"
    echo ""
    echo "Run the test with:"
    echo "./test_program_generation.sh $FIRST_USER_ID"
    exit 0
fi

# No users found, create a test user
echo "No users found. Creating test user..."
echo ""

# Generate UUID for new user
NEW_USER_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

# Create test user
psql "$DATABASE_URL" -c "
INSERT INTO users (id, name, email, password_hash, created_at, updated_at)
VALUES (
    '$NEW_USER_ID'::uuid,
    'Test User',
    'test@nowva.ai',
    'test_hash_not_for_login',
    NOW(),
    NOW()
)
ON CONFLICT (email) DO NOTHING;
" 2>/dev/null

# Check if creation succeeded
CHECK_USER=$(psql "$DATABASE_URL" -t -c "SELECT id FROM users WHERE id = '$NEW_USER_ID'::uuid;" 2>/dev/null | tr -d ' ')

if [ -n "$CHECK_USER" ]; then
    echo "✅ Test user created successfully!"
    echo ""
    psql "$DATABASE_URL" -c "SELECT id, name, email, created_at FROM users WHERE id = '$NEW_USER_ID'::uuid;"
    echo ""
    echo "📋 Use this User ID for testing:"
    echo "$NEW_USER_ID"
    echo ""
    echo "Run the test with:"
    echo "./test_program_generation.sh $NEW_USER_ID"
else
    # Try to get user by email (might already exist)
    EXISTING_EMAIL_USER=$(psql "$DATABASE_URL" -t -c "SELECT id FROM users WHERE email = 'test@nowva.ai';" 2>/dev/null | tr -d ' ')

    if [ -n "$EXISTING_EMAIL_USER" ]; then
        echo "✅ Test user already exists with that email!"
        echo ""
        psql "$DATABASE_URL" -c "SELECT id, name, email, created_at FROM users WHERE email = 'test@nowva.ai';"
        echo ""
        echo "📋 Use this User ID for testing:"
        echo "$EXISTING_EMAIL_USER"
        echo ""
        echo "Run the test with:"
        echo "./test_program_generation.sh $EXISTING_EMAIL_USER"
    else
        echo "❌ Failed to create test user"
        echo ""
        echo "You may need to create a user manually through your application"
    fi
fi
