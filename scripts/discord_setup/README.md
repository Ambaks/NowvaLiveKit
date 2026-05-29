# Nowva AI Discord Server Setup

Automated setup script that creates all categories, channels, roles, topics, and pinned messages for the Nowva AI team Discord server.

## Prerequisites

Before running the script, you need to manually create two things: the Discord server and a bot application.

### Step 1: Create the Discord server

1. Open Discord (app or browser)
2. Click the **+** button in the left sidebar
3. Choose **Create My Own** > **For me and my friends**
4. Name it **Nowva AI**
5. Click **Create**

### Step 2: Create a bot application

1. Go to https://discord.com/developers/applications
2. Click **New Application**, name it **Nowva Setup Bot**
3. Go to the **Bot** tab in the left sidebar
4. Click **Reset Token**, then **Copy** the token — save it somewhere safe
5. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent**
   - **Message Content Intent**
6. Click **Save Changes**

### Step 3: Invite the bot to your server

1. Go to the **OAuth2** tab in the left sidebar
2. Under **OAuth2 URL Generator**, check the **bot** scope
3. Under **Bot Permissions**, check **Administrator**
4. Copy the generated URL at the bottom
5. Open it in your browser, select **Nowva AI** server, click **Authorize**

### Step 4: Get the server (guild) ID

1. In Discord, go to **User Settings** > **Advanced** > enable **Developer Mode**
2. Right-click the **Nowva AI** server icon in the left sidebar
3. Click **Copy Server ID**

### Step 5: Configure and run

```bash
cd scripts/discord_setup

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
# Edit .env and paste your BOT_TOKEN and GUILD_ID

# Preview what will be created
python setup.py --dry-run

# Run the setup
python setup.py

# If you need to start over
python setup.py --teardown
python setup.py
```

## What gets created

| Type | Count | Details |
|------|-------|---------|
| Roles | 6 | CEO, Cofounder, Hardware, Advisor, Investor, Bot |
| Categories | 4 | General, Engineering, Product, Integrations |
| Text channels | 14 | welcome, announcements, standups, random, dev-general, biomechanics, voice-and-llm, frontend, hardware, infra, product, bugs, github, bot-logs |
| Voice channels | 2 | General Voice, Pair Programming |
| Pinned messages | 2 | #welcome intro, #standups template |

## Flags

- `--dry-run` — prints the full plan without making any changes
- `--teardown` — removes all channels, categories, and roles created by this script

The script is idempotent: running it twice won't duplicate anything.

## After setup

See the manual checklist in the setup log for things bots can't automate (server icon, GitHub webhooks, etc.).
