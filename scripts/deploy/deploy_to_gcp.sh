#!/bin/bash
# Quick deployment script for GCP Free Tier
# Run this from your LOCAL machine

set -e

echo "=========================================="
echo "NowvaLiveKit - GCP Deployment Script"
echo "=========================================="

# Configuration
VM_NAME="nova-ai-website"  # Change this to your VM name
ZONE="us-central1-c"  # Change this to your zone
PROJECT_DIR="/home/$USER/nowva"

echo ""
echo "Configuration:"
echo "  VM: $VM_NAME"
echo "  Zone: $ZONE"
echo "  Remote dir: $PROJECT_DIR"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Step 1: Build frontend
echo "Step 1/4: Building frontend..."
cd frontend_demo
npm run build
cd ..

# Step 2: Create deployment archive
echo "Step 2/4: Creating deployment archive..."
tar --exclude='*.pyc' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.DS_Store' \
  -czf nowva-deploy.tar.gz \
  src/ \
  frontend_demo/dist/ \
  config/gunicorn_config_gcp.py \
  requirements-server.txt \
  .env \
  shell/server_setup.sh \
  shell/server_monitor.sh

echo "Archive size:"
du -h nowva-deploy.tar.gz

# Step 3: Upload to VM
echo "Step 3/4: Uploading to VM..."
gcloud compute scp nowva-deploy.tar.gz $VM_NAME:~ --zone=$ZONE

# Step 4: Deploy on VM
echo "Step 4/4: Deploying on VM..."
gcloud compute ssh $VM_NAME --zone=$ZONE --command="
  set -e
  echo 'Extracting archive...'
  cd $PROJECT_DIR
  tar -xzf ~/nowva-deploy.tar.gz

  echo 'Activating virtual environment...'
  source venv/bin/activate

  echo 'Restarting services...'
  sudo systemctl restart nowva-api
  sudo systemctl restart nowva-celery
  sudo systemctl restart nowva-livekit-agent

  echo 'Waiting for services to start...'
  sleep 5

  echo 'Checking service status...'
  sudo systemctl is-active nowva-api nowva-celery nowva-livekit-agent

  echo 'Testing health endpoint...'
  curl -f http://localhost:8000/api/health || echo 'Health check failed!'

  echo ''
  echo '✓ Deployment complete!'
  echo ''
  echo 'View logs with:'
  echo '  sudo journalctl -u nowva-api -f'
  echo '  tail -f $PROJECT_DIR/logs/gunicorn_error.log'
"

echo ""
echo "=========================================="
echo "✓ Deployment Complete!"
echo "=========================================="
echo ""
echo "Your app is now running at:"
echo "  External IP: http://$(gcloud compute instances describe $VM_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)')"
echo ""
echo "Check status:"
echo "  gcloud compute ssh $VM_NAME --zone=$ZONE --command='sudo systemctl status nowva-api nowva-celery nowva-livekit-agent'"
echo ""

# Cleanup
rm nowva-deploy.tar.gz


