# AWS EC2 Deployment Guide - Job Scrapper

## Server Info

| Field         | Value                                                         |
|---------------|---------------------------------------------------------------|
| **Instance**  | EC2 (Ubuntu 24.04 LTS) - `ap-south-1` (Mumbai)               |
| **Public DNS**| `ec2-13-233-86-11.ap-south-1.compute.amazonaws.com`           |
| **Private IP**| `172.31.35.2`                                                 |
| **SSH Key**   | `aws/scoutit-scrapper.pem`                                    |
| **User**      | `ubuntu`                                                      |
| **App Path**  | `/home/ubuntu/job-scrapper`                                   |
| **App URL**   | `http://ec2-13-233-86-11.ap-south-1.compute.amazonaws.com`    |

---

## Prerequisites

- SSH key file (`aws/scoutit-scrapper.pem`) in the project root
- EC2 Security Group with ports **22 (SSH)** and **80 (HTTP)** open

---

## 1. Connect to Your VPS

```bash
# Set correct permissions on the key file (required, do this once)
chmod 400 aws/scoutit-scrapper.pem

# SSH into the server
ssh -i "aws/scoutit-scrapper.pem" ubuntu@ec2-13-233-86-11.ap-south-1.compute.amazonaws.com
```

---

## 2. Transfer Code to VPS

Use `rsync` from your local machine to push code to the VPS (excludes venv, cache, credentials, etc.):

```bash
rsync -avz --progress \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.git/' \
  --exclude 'aws/' \
  --exclude 'logs/' \
  --exclude 'db.sqlite3' \
  --exclude '.env' \
  --exclude '.DS_Store' \
  --exclude 'staticfiles/' \
  --exclude 'output/' \
  --exclude '*.log' \
  -e "ssh -i aws/scoutit-scrapper.pem" \
  ./ \
  ubuntu@ec2-13-233-86-11.ap-south-1.compute.amazonaws.com:~/job-scrapper/
```

> **First time?** If you get `Host key verification failed`, add the host key first:
> ```bash
> ssh-keyscan -H ec2-13-233-86-11.ap-south-1.compute.amazonaws.com >> ~/.ssh/known_hosts
> ```

---

## 3. Run the Automated Setup

SSH into the VPS and run the setup script:

```bash
ssh -i "aws/scoutit-scrapper.pem" ubuntu@ec2-13-233-86-11.ap-south-1.compute.amazonaws.com

cd ~/job-scrapper
bash deploy/setup.sh
```

Or run it remotely in one shot:

```bash
ssh -i "aws/scoutit-scrapper.pem" ubuntu@ec2-13-233-86-11.ap-south-1.compute.amazonaws.com \
  "cd ~/job-scrapper && bash deploy/setup.sh"
```

The setup script installs and configures:

| Step | What it does                                                |
|------|-------------------------------------------------------------|
| 1    | System packages (python3, pip, venv, nginx, build tools)    |
| 2    | **MongoDB 7.0** - installed, enabled, started               |
| 3    | **Google Chrome** - for Selenium headless scrapers           |
| 4    | Python venv + `pip install -r requirements/production.txt`   |
| 5    | `.env` file with auto-generated `DJANGO_SECRET_KEY`          |
| 6    | Django `migrate` + `collectstatic`                           |
| 7    | **Gunicorn** systemd service (auto-starts on boot/crash)     |
| 8    | **Nginx** reverse proxy on port 80                           |

---

## 4. Verify the Setup

```bash
# Check all services
sudo systemctl status job-scrapper   # Gunicorn (Django app)
sudo systemctl status nginx          # Nginx
sudo systemctl status mongod         # MongoDB

# Test locally
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost
```

Then open in your browser:
```
http://ec2-13-233-86-11.ap-south-1.compute.amazonaws.com
```

---

## 5. EC2 Security Group Setup

Make sure your EC2 instance's security group allows inbound traffic:

| Type  | Port | Source     | Purpose      |
|-------|------|-----------|--------------|
| SSH   | 22   | Your IP   | SSH access   |
| HTTP  | 80   | 0.0.0.0/0 | Web traffic |

To configure:
1. Go to **AWS Console** → **EC2** → **Instances**
2. Select your instance → **Security** tab → Click on the security group
3. **Edit inbound rules** → Add rules for port 22 and 80

---

## Architecture

```
Client Request (port 80)
    │
    ▼
┌─────────┐
│  Nginx  │  ← Reverse proxy, serves static files
└────┬────┘
     │ proxy_pass :8000
     ▼
┌───────────┐
│ Gunicorn  │  ← WSGI server (5 workers), runs Django app
│ (systemd) │     auto-restarts on crash/reboot
└────┬──────┘
     │
     ▼
┌─────────┐
│ MongoDB │  ← Job data storage (jobs_db)
└─────────┘
```

---

## Common Commands

### Application Management

```bash
# Restart the app (after code changes)
sudo systemctl restart job-scrapper

# Stop the app
sudo systemctl stop job-scrapper

# Start the app
sudo systemctl start job-scrapper

# Check app status
sudo systemctl status job-scrapper
```

### Viewing Logs

```bash
# Application logs (systemd/journald)
sudo journalctl -u job-scrapper -f

# Gunicorn access logs
tail -f ~/job-scrapper/logs/gunicorn-access.log

# Gunicorn error logs
tail -f ~/job-scrapper/logs/gunicorn-error.log

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Nginx

```bash
# Test config after changes
sudo nginx -t

# Reload (no downtime)
sudo systemctl reload nginx

# Restart
sudo systemctl restart nginx
```

### MongoDB

```bash
# Check status
sudo systemctl status mongod

# Open MongoDB shell
mongosh

# View jobs database
mongosh
> use jobs_db
> db.jobs.countDocuments()
```

---

## Deploying Updates

### Option A: Using rsync (from local machine)

```bash
# Transfer updated code
rsync -avz --progress \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.git/' \
  --exclude 'aws/' \
  --exclude 'logs/' \
  --exclude 'db.sqlite3' \
  --exclude '.env' \
  --exclude '.DS_Store' \
  --exclude 'staticfiles/' \
  --exclude 'output/' \
  --exclude '*.log' \
  -e "ssh -i aws/scoutit-scrapper.pem" \
  ./ \
  ubuntu@ec2-13-233-86-11.ap-south-1.compute.amazonaws.com:~/job-scrapper/

# Then SSH in and restart
ssh -i "aws/scoutit-scrapper.pem" ubuntu@ec2-13-233-86-11.ap-south-1.compute.amazonaws.com \
  "cd ~/job-scrapper && source venv/bin/activate && pip install -r requirements/production.txt && python manage.py migrate --noinput && python manage.py collectstatic --noinput && sudo systemctl restart job-scrapper"
```

### Option B: Using git (on VPS)

```bash
cd ~/job-scrapper
git pull
source venv/bin/activate
pip install -r requirements/production.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
sudo systemctl restart job-scrapper
```

### Quick Deploy One-Liner (on VPS)

```bash
cd ~/job-scrapper && git pull && source venv/bin/activate && pip install -r requirements/production.txt && python manage.py migrate --noinput && python manage.py collectstatic --noinput && sudo systemctl restart job-scrapper
```

---

## Running Scrapers on the VPS

```bash
cd ~/job-scrapper
source venv/bin/activate

# Scrape all companies
python run.py scrape --workers 10

# Scrape a single company
python run.py scrape --company Google

# Scrape with custom timeout
python run.py scrape --workers 15 --timeout 120
```

> Scrapers use Chrome headless via Selenium. Chrome is installed by the setup script.

---

## Environment Variables

The `.env` file is located at `~/job-scrapper/.env`:

```env
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=jobs_db

# Django
DJANGO_SECRET_KEY=<auto-generated>
DJANGO_ENV=production
ALLOWED_HOSTS=ec2-13-233-86-11.ap-south-1.compute.amazonaws.com,localhost,127.0.0.1
```

After editing `.env`, restart the app:
```bash
sudo systemctl restart job-scrapper
```

---

## File Structure on VPS

```
/home/ubuntu/job-scrapper/
├── deploy/
│   ├── AWS_DEPLOYMENT.md      # This file
│   ├── setup.sh               # Automated setup script
│   ├── gunicorn_config.py     # Gunicorn worker settings
│   ├── gunicorn.service       # Systemd service definition
│   └── nginx.conf             # Nginx site config
├── config/
│   ├── settings/
│   │   ├── base.py            # Shared settings
│   │   ├── production.py      # Production overrides (DEBUG=False)
│   │   └── development.py     # Dev overrides
│   ├── urls.py                # URL routing
│   ├── wsgi.py                # WSGI entry point
│   └── scraper.py             # Scraper config (275 companies)
├── apps/
│   ├── dashboard/             # Web UI
│   ├── scraper_manager/       # Scraper control API
│   └── data_store/            # Jobs data API
├── scrapers/                  # 275 company scraper files
├── core/                      # Shared utilities (MongoDB, logging)
├── scripts/                   # Management scripts
├── staticfiles/               # Collected static files (auto-generated)
├── logs/                      # Application logs
├── venv/                      # Python virtual environment
├── .env                       # Environment variables (not in git)
├── manage.py                  # Django management
├── run.py                     # CLI entry point
└── requirements/
    ├── base.txt               # Core dependencies
    └── production.txt         # Production deps (includes gunicorn)
```

---

## Systemd Service Config

Location: `/etc/systemd/system/job-scrapper.service`

Source: `deploy/gunicorn.service`

If you edit the service file, reload systemd:
```bash
sudo cp ~/job-scrapper/deploy/gunicorn.service /etc/systemd/system/job-scrapper.service
sudo systemctl daemon-reload
sudo systemctl restart job-scrapper
```

---

## Nginx Config

Location: `/etc/nginx/sites-available/job-scrapper`

Source: `deploy/nginx.conf`

If you edit the nginx config:
```bash
sudo cp ~/job-scrapper/deploy/nginx.conf /etc/nginx/sites-available/job-scrapper
sudo nginx -t
sudo systemctl reload nginx
```

---

## Troubleshooting

### App not starting

```bash
# Check service logs
sudo journalctl -u job-scrapper -n 50

# Try running Gunicorn manually to see errors
cd ~/job-scrapper
source venv/bin/activate
gunicorn config.wsgi:application --bind 127.0.0.1:8000
```

### 502 Bad Gateway

Nginx is running but can't reach Gunicorn:
```bash
# Check if Gunicorn is running
sudo systemctl status job-scrapper

# Restart it
sudo systemctl restart job-scrapper
```

### Static files not loading

```bash
cd ~/job-scrapper
source venv/bin/activate
python manage.py collectstatic --noinput
sudo systemctl reload nginx
```

### MongoDB connection error

```bash
# Check if MongoDB is running
sudo systemctl status mongod

# Start it
sudo systemctl start mongod

# Check MongoDB logs
sudo tail -f /var/log/mongodb/mongod.log
```

### Chrome / Selenium errors

```bash
# Verify Chrome is installed
google-chrome --version

# If missing, reinstall
wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt-get install -y /tmp/google-chrome.deb
```

### Permission denied errors

```bash
# Fix ownership (all files should be owned by ubuntu)
sudo chown -R ubuntu:ubuntu ~/job-scrapper
```

### Port 80 not accessible

Check your EC2 Security Group inbound rules (see Section 5 above).

### DNS changed after instance stop/start

EC2 public DNS changes when you stop and start an instance. Update these:
```bash
# 1. Update .env on VPS
nano ~/job-scrapper/.env
# Change ALLOWED_HOSTS to new DNS

# 2. Update Nginx config
sudo nano /etc/nginx/sites-available/job-scrapper
# Change server_name to new DNS

# 3. Restart services
sudo systemctl restart job-scrapper
sudo systemctl reload nginx
```

> To avoid this, attach an **Elastic IP** to your instance in the AWS Console.
