# Fix: "Waiting for Audio" Issue on nowvasports.com

## 🐛 The Problem

When users click "Talk to Nova" on your production site, they get stuck on "waiting for audio" because the **LiveKit Website Voice Agent worker is not running** on your production server.

Your production deployment has been running:
1. ✅ FastAPI (nowva-api) - Handles API requests
2. ✅ Celery Workers (nowva-celery) - Generates programs in background
3. ✅ Redis - Message broker
4. ❌ **LiveKit Agent** - MISSING! This is the voice agent that talks to users

## ✅ The Solution

I've updated your deployment scripts to include the missing LiveKit agent service:

### Updated Files:
- [server_setup.sh](server_setup.sh) - Now creates `nowva-livekit-agent.service`
- [deploy_to_gcp.sh](deploy_to_gcp.sh) - Now restarts the agent on deployments

## 🚀 How to Fix Your Production Server

### Option 1: Quick Fix (Recommended)

SSH into your server and manually start the agent:

```bash
# SSH into your production server
gcloud compute ssh nowva-instance --zone=us-central1-c

# Navigate to project directory
cd /home/$USER/nowva
source venv/bin/activate

# Create the systemd service file
sudo bash -c 'cat > /etc/systemd/system/nowva-livekit-agent.service << '\''EOF'\''
[Unit]
Description=Nowva LiveKit Website Voice Agent
After=network.target nowva-api.service
Wants=nowva-api.service

[Service]
Type=simple
User='$USER'
Group=www-data
WorkingDirectory=/home/'$USER'/nowva
Environment="PATH=/home/'$USER'/nowva/venv/bin"
Environment="PYTHONPATH=/home/'$USER'/nowva/src"
ExecStart=/home/'$USER'/nowva/venv/bin/python3 src/agents/website_voice_agent.py

Restart=always
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=30

StandardOutput=append:/home/'$USER'/nowva/logs/livekit_agent_stdout.log
StandardError=append:/home/'$USER'/nowva/logs/livekit_agent_stderr.log

[Install]
WantedBy=multi-user.target
EOF'

# Reload systemd and start the service
sudo systemctl daemon-reload
sudo systemctl enable nowva-livekit-agent
sudo systemctl start nowva-livekit-agent

# Check if it's running
sudo systemctl status nowva-livekit-agent
```

### Option 2: Full Redeploy (Comprehensive)

From your local machine:

```bash
# This will redeploy everything with the updated setup script
./deploy_to_gcp.sh
```

Then SSH into the server and run:

```bash
cd /home/$USER/nowva
./server_setup.sh
```

This will recreate all services including the new LiveKit agent.

## 🔍 Verify It's Working

After starting the agent, test it:

```bash
# Check all services are running
sudo systemctl status nowva-api nowva-celery nowva-livekit-agent

# View agent logs (should show "Starting...")
tail -f /home/$USER/nowva/logs/livekit_agent_stdout.log

# Check for errors
tail -f /home/$USER/nowva/logs/livekit_agent_stderr.log
```

Then visit nowvasports.com and click "Talk to Nova" - it should connect!

## 📊 What the LiveKit Agent Does

When running, the agent:
1. Connects to LiveKit server (wss://nowva-k5kvmizx.livekit.cloud)
2. Listens for new rooms being created
3. When a user clicks "Talk to Nova":
   - User gets token from your API
   - User joins LiveKit room
   - **Agent automatically joins the same room**
   - Agent starts conversation: "Hi! What's your first name?"
4. Agent guides user through program creation questions
5. Agent calls your API to generate the program
6. User receives email with their program

## 🔄 Production Architecture (Now Complete)

```
Production Server (nowvasports.com)
├── nginx (port 80/443) ───────────┐
│                                   │
├── nowva-api.service              │
│   └── Gunicorn + FastAPI :8000 ──┘
│
├── nowva-celery.service
│   └── 3 workers (background program generation)
│
├── nowva-livekit-agent.service  ← NEW!
│   └── LiveKit voice agent worker
│
└── redis-server.service
    └── Message broker for Celery
```

## 🎯 Next Steps

1. **Deploy the fix** using Option 1 or 2 above
2. **Test the voice interface** - click "Talk to Nova" on your site
3. **Monitor the logs** to ensure it's working:
   ```bash
   # Watch agent logs in real-time
   tail -f logs/livekit_agent_stdout.log

   # Check for any errors
   grep ERROR logs/livekit_agent_stderr.log
   ```

## 💡 Why This Happened

The LiveKit agent was missing from your original `server_setup.sh` script. The script only set up:
- FastAPI for the web server
- Celery for background jobs
- But **not** the LiveKit agent for voice conversations

The agent works fine on localhost because you manually run `./start_website_agent.sh`, but in production it needs to run as a systemd service.

## ✅ Prevention

The updated deployment scripts now ensure the LiveKit agent is:
- ✅ Created as a systemd service
- ✅ Started automatically on server boot
- ✅ Restarted on crashes
- ✅ Logs to dedicated log files
- ✅ Included in deployment health checks

---

**Questions?** Check logs:
- Agent logs: `tail -f logs/livekit_agent_stdout.log`
- API logs: `sudo journalctl -u nowva-api -f`
- Celery logs: `tail -f logs/celery/worker.log`
