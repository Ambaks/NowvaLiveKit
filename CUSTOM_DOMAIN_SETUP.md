# Custom Domain Setup Guide

## Prerequisites
- ✅ You have a domain name (e.g., `nowva.ai`)
- ✅ Production services are running (Redis, Celery, Gunicorn)
- ✅ nginx is installed

---

## Step 1: Configure Your Domain DNS

### Get Your Mac's IP Address

```bash
# Get local IP address
ifconfig | grep "inet " | grep -v 127.0.0.1
```

### Configure DNS Records

In your domain registrar (GoDaddy, Namecheap, Cloudflare, etc.):

1. **A Record**:
   - Name: `@` (or your subdomain like `app`)
   - Type: `A`
   - Value: Your Mac's **public IP address**
   - TTL: 3600 (1 hour)

2. **Optional CNAME for www**:
   - Name: `www`
   - Type: `CNAME`
   - Value: `yourdomain.com`

**Note**: If you're behind a router, you need to:
- Set up port forwarding: `80 → your Mac's local IP → 80` and `443 → 443`
- Or use a service like ngrok or Cloudflare Tunnel for testing

---

## Step 2: Update nginx Configuration

### Edit the Configuration File

```bash
# Open the nginx config
nano nginx_production.conf
```

Replace all instances of `yourdomain.com` with your actual domain (e.g., `nowva.ai`).

### Copy to nginx Directory

```bash
# Copy the config to nginx sites directory
sudo cp nginx_production.conf /opt/homebrew/etc/nginx/servers/nowva.conf

# Test the configuration
sudo nginx -t

# If test passes, reload nginx
brew services restart nginx
```

---

## Step 3: Test HTTP Access (Before SSL)

### Temporarily Enable HTTP-Only Mode

1. Edit `nginx_production.conf`
2. Comment out the HTTPS server block (lines with `listen 443`)
3. Uncomment the temporary HTTP server block at the bottom
4. Reload nginx: `brew services restart nginx`

### Test Your Domain

```bash
# Test from command line
curl -I http://yourdomain.com

# Or open in browser
open http://yourdomain.com
```

**Expected**: You should see your frontend loading!

---

## Step 4: Set Up SSL Certificate (HTTPS)

### Install Certbot

```bash
brew install certbot
```

### Stop nginx Temporarily

```bash
brew services stop nginx
```

### Get SSL Certificate

```bash
# Replace with your actual domain and email
sudo certbot certonly --standalone \
  -d yourdomain.com \
  -d www.yourdomain.com \
  --email your-email@example.com \
  --agree-tos
```

### Verify Certificate Files

```bash
# Check if certificates were created
ls -la /etc/letsencrypt/live/yourdomain.com/
```

You should see:
- `fullchain.pem`
- `privkey.pem`

### Update nginx Config for SSL

1. Edit `nginx_production.conf`
2. Update the SSL certificate paths to match your domain:
   ```nginx
   ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
   ```
3. Uncomment the HTTPS server block (remove the temporary HTTP block)
4. Copy updated config: `sudo cp nginx_production.conf /opt/homebrew/etc/nginx/servers/nowva.conf`

### Start nginx

```bash
brew services start nginx
```

### Test HTTPS

```bash
curl -I https://yourdomain.com
# Should return 200 OK with SSL

# Open in browser
open https://yourdomain.com
```

---

## Step 5: Update Frontend Environment Variables

### Edit Frontend .env

```bash
cd frontend_demo
nano .env
```

Update the API URL to use your domain:

```env
VITE_API_URL=https://yourdomain.com/api
VITE_LIVEKIT_URL=wss://nowva-k5kvmizx.livekit.cloud
```

### Rebuild Frontend

```bash
npm run build
```

### Restart Gunicorn

```bash
# Stop current Gunicorn
pkill -f "gunicorn.*src.api.main:app"

# Start with updated frontend
cd ..
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"
export PYTHONPATH='src'
nohup gunicorn -c gunicorn_config.py src.api.main:app > logs/gunicorn_startup.log 2>&1 &
```

---

## Step 6: Update CORS Settings (Optional)

### Edit FastAPI CORS Settings

If you want to restrict CORS to your domain only:

```bash
nano src/api/main.py
```

Change:
```python
allow_origins=["*"]  # Allow all
```

To:
```python
allow_origins=[
    "https://yourdomain.com",
    "https://www.yourdomain.com",
    "http://localhost:5173"  # Keep for local development
]
```

Then restart Gunicorn.

---

## Step 7: Set Up SSL Auto-Renewal

Let's Encrypt certificates expire every 90 days. Set up auto-renewal:

```bash
# Test renewal process
sudo certbot renew --dry-run

# If successful, add a cron job
sudo crontab -e
```

Add this line to renew daily at 2 AM:
```
0 2 * * * certbot renew --quiet --post-hook "brew services reload nginx"
```

---

## Verification Checklist

Once everything is set up:

- [ ] Domain DNS resolves to your IP: `dig yourdomain.com`
- [ ] HTTP redirects to HTTPS: `curl -I http://yourdomain.com`
- [ ] HTTPS works: `curl -I https://yourdomain.com`
- [ ] Frontend loads: Open `https://yourdomain.com` in browser
- [ ] API works: `curl https://yourdomain.com/api/health`
- [ ] API docs accessible: Open `https://yourdomain.com/docs`
- [ ] SSL certificate is valid: Check browser lock icon

---

## Production Stack Status

Your production stack should now be:

```
Internet
   ↓
[Your Domain DNS] → [Your Public IP]
   ↓
[Router Port Forwarding] → 80/443
   ↓
[nginx] → HTTPS/SSL Termination
   ↓
[Gunicorn :8000] → FastAPI + Frontend
   ↓
[Celery Workers] ← [Redis] → Background Jobs
   ↓
[PostgreSQL (Neon)] → Database
```

---

## Troubleshooting

### Domain doesn't resolve
```bash
# Check DNS propagation
dig yourdomain.com

# May take 24-48 hours for DNS to propagate globally
# Use https://dnschecker.org to check status
```

### nginx 502 Bad Gateway
```bash
# Check if Gunicorn is running
ps aux | grep gunicorn

# Check nginx error logs
tail -f /opt/homebrew/var/log/nginx/error.log
```

### SSL Certificate Errors
```bash
# Check certificate validity
sudo certbot certificates

# Renew manually if needed
sudo certbot renew --force-renewal
```

### Can't Access from Outside Network
- Verify port forwarding on your router (80 and 443)
- Check firewall settings: `sudo pfctl -s all`
- Try accessing from your phone using cellular data (not WiFi)

---

## Quick Commands Reference

```bash
# Start all production services
./start_celery_workers.sh
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"
export PYTHONPATH='src'
nohup gunicorn -c gunicorn_config.py src.api.main:app > logs/gunicorn_startup.log 2>&1 &

# Check nginx status
brew services list | grep nginx

# Reload nginx config (without downtime)
brew services reload nginx

# Test nginx config
sudo nginx -t

# View nginx logs
tail -f /opt/homebrew/var/log/nginx/access.log
tail -f /opt/homebrew/var/log/nginx/error.log

# Check SSL certificate expiry
sudo certbot certificates

# Manual SSL renewal
sudo certbot renew
```

---

## Next Steps

1. **Set up monitoring**: Use tools like UptimeRobot to monitor uptime
2. **Configure backups**: Regular database and file backups
3. **Add analytics**: Google Analytics or similar
4. **Rate limiting**: Consider adding nginx rate limiting for DDoS protection
5. **CDN**: Consider Cloudflare for better performance and DDoS protection

---

## 🎉 Your Application is Now Live!

Your Nowva application is now accessible at:
- **Website**: https://yourdomain.com
- **API**: https://yourdomain.com/api
- **API Docs**: https://yourdomain.com/docs
