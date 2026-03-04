#!/bin/bash
set -e

# ============================================================
# VPS Setup Script for Job Scrapper Django Application
# Run this on your Ubuntu VPS as the 'ubuntu' user
# Usage: bash deploy/setup.sh
# ============================================================

APP_DIR="/home/ubuntu/job-scrapper"
PYTHON_VERSION="python3"

echo "========================================="
echo "  Job Scrapper - VPS Setup"
echo "========================================="

# --------------------------------------------------
# 1. System packages
# --------------------------------------------------
echo ""
echo "[1/8] Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    nginx \
    curl wget unzip gnupg \
    build-essential libffi-dev libssl-dev

# --------------------------------------------------
# 2. Install MongoDB 7.0
# --------------------------------------------------
echo ""
echo "[2/8] Installing MongoDB..."
if ! command -v mongod &> /dev/null; then
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
        sudo gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg
    echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
        sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
    sudo apt-get update
    sudo apt-get install -y mongodb-org
    sudo systemctl enable mongod
    sudo systemctl start mongod
    echo "  MongoDB installed and started."
else
    echo "  MongoDB already installed, ensuring it's running..."
    sudo systemctl enable mongod
    sudo systemctl start mongod
fi

# --------------------------------------------------
# 3. Install Google Chrome (for Selenium scrapers)
# --------------------------------------------------
echo ""
echo "[3/8] Installing Google Chrome..."
if ! command -v google-chrome &> /dev/null; then
    wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt-get install -y /tmp/google-chrome.deb || sudo apt-get install -f -y
    rm /tmp/google-chrome.deb
    echo "  Chrome installed: $(google-chrome --version)"
else
    echo "  Chrome already installed: $(google-chrome --version)"
fi

# --------------------------------------------------
# 4. Python virtual environment & dependencies
# --------------------------------------------------
echo ""
echo "[4/8] Setting up Python environment..."
cd "$APP_DIR"

if [ ! -d "venv" ]; then
    $PYTHON_VERSION -m venv venv
    echo "  Virtual environment created."
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements/production.txt
echo "  Dependencies installed."

# --------------------------------------------------
# 5. Environment file
# --------------------------------------------------
echo ""
echo "[5/8] Setting up environment file..."
if [ ! -f ".env" ]; then
    # Generate a random Django secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")

    cat > .env << EOF
# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=jobs_db

# Django
DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_ENV=production
ALLOWED_HOSTS=ec2-13-233-86-11.ap-south-1.compute.amazonaws.com,localhost,127.0.0.1
EOF
    echo "  .env file created with a generated secret key."
else
    echo "  .env file already exists, skipping."
    # Ensure DJANGO_ENV is set to production
    if ! grep -q "DJANGO_ENV=production" .env; then
        echo "  WARNING: Make sure DJANGO_ENV=production is set in your .env file!"
    fi
fi

# --------------------------------------------------
# 6. Django setup (migrate, collectstatic)
# --------------------------------------------------
echo ""
echo "[6/8] Running Django setup..."
mkdir -p logs

python manage.py migrate --noinput
echo "  Migrations applied."

python manage.py collectstatic --noinput
echo "  Static files collected."

# --------------------------------------------------
# 7. Gunicorn systemd service
# --------------------------------------------------
echo ""
echo "[7/8] Setting up Gunicorn service..."
sudo cp deploy/gunicorn.service /etc/systemd/system/job-scrapper.service
sudo systemctl daemon-reload
sudo systemctl enable job-scrapper
sudo systemctl restart job-scrapper
echo "  Gunicorn service enabled and started."

# --------------------------------------------------
# 8. Nginx configuration
# --------------------------------------------------
echo ""
echo "[8/8] Setting up Nginx..."
sudo rm -f /etc/nginx/sites-enabled/default
sudo cp deploy/nginx.conf /etc/nginx/sites-available/job-scrapper
sudo ln -sf /etc/nginx/sites-available/job-scrapper /etc/nginx/sites-enabled/job-scrapper

# Test nginx config
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
echo "  Nginx configured and restarted."

# --------------------------------------------------
# Done!
# --------------------------------------------------
echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "  App URL: http://ec2-13-233-86-11.ap-south-1.compute.amazonaws.com"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status job-scrapper   # Check app status"
echo "    sudo systemctl restart job-scrapper   # Restart app"
echo "    sudo journalctl -u job-scrapper -f    # View app logs"
echo "    sudo systemctl status nginx           # Check Nginx"
echo "    tail -f logs/gunicorn-error.log       # Gunicorn errors"
echo ""
