# PUMO TECHNOVATION EXAM PORTAL – PRODUCTION DEPLOYMENT & HOSTING GUIDE
**Branch:** POONAMALLEE  
**Developed By:** Team SAT  
**Copyright:** © 2026 PUMO TECHNOVATION. All Rights Reserved.

---

## 1. System Overview & Architecture

The **PUMO TECHNOVATION Exam Portal** is an enterprise-grade academic and practical examination management platform built with:
- **Backend:** Django 5.x (Python 3.10+)
- **Database:** MySQL 8.x
- **Frontend:** Bootstrap 5, FontAwesome, HTML5 Canvas Proctoring & Real-time Vision Tracking
- **Code Execution:** Sandboxed Subprocess Execution Engine for Python and Java with multi-test case verification
- **Document Processing:** PyMuPDF (`fitz`) and `pdfplumber` for structured OCR & PDF exam extraction

---

## 2. Pre-Requisites & Environment Setup

### 2.1 Hardware Requirements
- **CPU:** 2 Cores minimum (4+ Cores recommended for concurrent coding evaluations)
- **RAM:** 4 GB minimum (8 GB recommended)
- **Disk:** 20 GB SSD storage
- **OS:** Ubuntu 22.04 LTS / 24.04 LTS or Windows Server 2019/2022

### 2.2 Software Requirements
- Python 3.10, 3.11, or 3.12
- MySQL Server 8.0+
- Java Development Kit (JDK 17+) — *required for Java practical exams*
- Nginx (for Linux production reverse proxy) or Waitress/IIS (for Windows)
- Git

---

## 3. Ubuntu Linux Production Deployment (Nginx + Gunicorn + MySQL)

### Step 1: Update System & Install Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev default-jdk default-jre \
    mysql-server libmysqlclient-dev nginx certbot python3-certbot-nginx git
```

### Step 2: Configure MySQL Database
```bash
sudo mysql -u root -p
```
Run the following SQL commands:
```sql
CREATE DATABASE pumo_exam_portal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'pumo_admin'@'localhost' IDENTIFIED BY 'StrongPumoPassword2026!';
GRANT ALL PRIVILEGES ON pumo_exam_portal.* TO 'pumo_admin'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### Step 3: Clone Codebase & Setup Virtual Environment
```bash
cd /var/www
sudo git clone <your-repo-url> pumo_exam_portal
sudo chown -R $USER:$USER /var/www/pumo_exam_portal
cd /var/www/pumo_exam_portal

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

### Step 4: Configure Production Environment Variables (`.env`)
```bash
cp .env.example .env
nano .env
```
Ensure the values are set:
```ini
SECRET_KEY=generate-a-strong-random-50-char-secret-key-here
DEBUG=False
ALLOWED_HOSTS=exam.pumotechnovation.com,www.exam.pumotechnovation.com,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://exam.pumotechnovation.com,https://www.exam.pumotechnovation.com

DB_ENGINE=django.db.backends.mysql
DB_NAME=pumo_exam_portal
DB_USER=pumo_admin
DB_PASSWORD=StrongPumoPassword2026!
DB_HOST=127.0.0.1
DB_PORT=3306

TESSERACT_CMD=/usr/bin/tesseract
```

### Step 5: Run Database Migrations & Collect Static Files
```bash
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Create default superadmin account:
```bash
python manage.py createsuperuser
```

### Step 6: Create Systemd Gunicorn Service
Create `/etc/systemd/system/pumo_exam.service`:
```bash
sudo nano /etc/systemd/system/pumo_exam.service
```
Paste the following:
```ini
[Unit]
Description=Gunicorn daemon for PUMO Technovation Exam Portal
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/pumo_exam_portal
ExecStart=/var/www/pumo_exam_portal/venv/bin/gunicorn \
    --access-logfile - \
    --error-logfile /var/log/gunicorn/pumo_error.log \
    --workers 4 \
    --bind 127.0.0.1:8000 \
    config.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

Set permissions and start service:
```bash
sudo mkdir -p /var/log/gunicorn
sudo chown -R www-data:www-data /var/www/pumo_exam_portal/media
sudo chown -R www-data:www-data /var/log/gunicorn
sudo systemctl daemon-reload
sudo systemctl start pumo_exam
sudo systemctl enable pumo_exam
sudo systemctl status pumo_exam
```

### Step 7: Configure Nginx as Reverse Proxy
Create `/etc/nginx/sites-available/pumo_exam`:
```bash
sudo nano /etc/nginx/sites-available/pumo_exam
```
Configuration:
```nginx
server {
    listen 80;
    server_name exam.pumotechnovation.com www.exam.pumotechnovation.com;

    client_max_body_size 50M;

    location = /favicon.ico { 
        access_log off; 
        log_not_found off; 
    }

    location /static/ {
        alias /var/www/pumo_exam_portal/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location /media/ {
        alias /var/www/pumo_exam_portal/media/;
        expires 7d;
    }

    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

Enable site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/pumo_exam /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 8: Enable Free SSL with Let's Encrypt Certbot
```bash
sudo certbot --nginx -d exam.pumotechnovation.com -d www.exam.pumotechnovation.com
```

---

## 4. Windows Server Hosting (Waitress / Windows Service)

### Step 1: Install Waitress
In your Windows virtual environment:
```powershell
pip install waitress
```

### Step 2: Run with Waitress
```powershell
waitress-serve --port=8000 --threads=8 config.wsgi:application
```

### Step 3: Configure Windows Service (NSSM)
You can configure Waitress to run as a persistent Windows Service using **NSSM (Non-Sucking Service Manager)**:
1. Download NSSM from `https://nssm.cc`.
2. Run in Administrator PowerShell:
   ```powershell
   nssm install PumoExamPortal "E:\PUMO_EXAM_PORTAL\venv\Scripts\waitress-serve.exe" "--port=8000 --threads=8 config.wsgi:application"
   nssm set PumoExamPortal AppDirectory "E:\PUMO_EXAM_PORTAL"
   nssm set PumoExamPortal Start SERVICE_AUTO_START
   nssm start PumoExamPortal
   ```

---

## 5. Security & Production Checklist

1. **DEBUG Mode:** Ensure `DEBUG=False` in `.env`.
2. **Secret Key:** Use a randomly generated secret key not committed to git.
3. **Database Backups:** Setup automated daily MySQL dumps:
   ```bash
   mysqldump -u pumo_admin -p pumo_exam_portal > /backups/pumo_$(date +\%F).sql
   ```
4. **Media Permissions:** Ensure `/media/` folder is writable by the web server user.
5. **Webcam Proctoring Permissions:** HTTPS is mandatory in modern browsers for camera and microphone access. Certbot SSL ensures browser camera permissions work seamlessly.
6. **Compiler Sandbox:** For multi-language coding questions, verify both `python3` and `javac`/`java` are available in system PATH.

---

## 6. Support & Contact

- **Institution:** PUMO TECHNOVATION (Poonamallee Branch)
- **Developers:** Team SAT
- **System Version:** 2.0.0 Production Release (2026)
