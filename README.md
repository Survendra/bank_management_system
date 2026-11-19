# 🏦 BlueBank — Banking Management System

BlueBank is an educational banking management system built with **React, Flask, Python, and MongoDB Atlas**. The application provides secure account management, transactions, beneficiaries, cards, scheduled transfers, and administrative functionality.

> **Note:** BlueBank is an educational/demo banking application and is not intended for real banking transactions or production financial use.

---

## 🚀 Live Demo

**Application:**  
https://bluebank-demo.duckdns.org

**API Health Check:**  
https://bluebank-demo.duckdns.org/api/health

---

## ✨ Features

### 👤 Account Management
- Create bank accounts
- Login using account number and PIN
- View account details
- View account balance
- Update PIN
- Account security and lockout protection

### 💰 Banking Operations
- Deposit money
- Withdraw money
- Transfer funds
- Add and manage beneficiaries
- Transaction history
- Transaction details
- Scheduled transfers

### 💳 Card Management
- Card management
- Card information
- Card-related account functionality

### 🔐 Security
- PIN hashing using PBKDF2-SHA256
- Secure authentication
- PIN attempt protection
- Temporary account lockout
- 2FA support
- Security event tracking
- Secure Flask sessions
- HTTPS in production

### 👨‍💼 Staff/Admin
- Bank staff authentication
- Admin functionality
- Staff user configuration through environment variables

---

# 🛠️ Technology Stack

## Frontend

- React
- Vite
- JavaScript/TypeScript
- HTML
- CSS

## Backend

- Python
- Flask
- Gunicorn
- PyMongo
- Werkzeug

## Database

- MongoDB Atlas

## Deployment

- AWS EC2
- Amazon Linux 2023
- Docker
- Docker Compose
- Caddy
- DuckDNS

---

# 🏗️ Architecture

```text
                         Internet
                            |
                            v
                bluebank-demo.duckdns.org
                            |
                            v
                     AWS EC2 Instance
                            |
                            v
                    +---------------+
                    |     Caddy     |
                    |   HTTP/HTTPS  |
                    +-------+-------+
                            |
              +-------------+-------------+
              |                           |
              | /api/*                    | /*
              v                           v
       +-------------+             +-------------+
       | Flask API   |             | React       |
       | Gunicorn    |             | Frontend    |
       | :5000       |             | :80         |
       +------+------+             +-------------+
              |
              v
       +----------------+
       | MongoDB Atlas  |
       |   bluebank     |
       +----------------+

              ^
              |
       +------+------+
       |   Worker    |
       | Scheduled   |
       | Transfers   |
       +-------------+
```

---

# 📁 Project Structure

```text
bank_management_system/
│
├── backend/
│   ├── app.py
│   ├── bank_service.py
│   ├── scheduled_transfer_worker.py
│   └── ...
│
├── vite-project/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── ...
│
├── deploy/
│   └── aws/
│       ├── Caddyfile
│       ├── Dockerfile.backend
│       ├── Dockerfile.frontend
│       ├── nginx.conf
│       └── proxy_params
│
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .dockerignore
└── README.md
```

---

# ⚙️ Prerequisites

For local development:

- Python 3.x
- Node.js
- npm
- Git
- MongoDB Atlas account

For AWS deployment:

- AWS account
- EC2 instance
- MongoDB Atlas
- DuckDNS account
- Docker
- Docker Compose

---

# 🗄️ MongoDB Atlas Setup

BlueBank uses MongoDB Atlas for persistent data storage.

The application uses the following database:

```text
bluebank
```

Collections include:

```text
accounts
transactions
beneficiaries
cards
security_events
notifications
```

The backend connects using the `MONGO_URI` environment variable.

Example:

```env
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
```

> Keep the MongoDB connection string private.

---

# 💻 Local Backend Setup

Clone the repository:

```bash
git clone https://github.com/Survendra/bank_management_system.git
cd bank_management_system
```

Create and activate a Python virtual environment:

### Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Linux/macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

Configure environment variables using `.env.example`:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Update `.env` with your MongoDB Atlas connection string and application configuration.

Run the Flask application:

```bash
python backend/app.py
```

The backend will be available on:

```text
http://localhost:5000
```

---

# 🌐 Local Frontend Setup

Go to the frontend directory:

```bash
cd vite-project
```

Install dependencies:

```bash
npm install
```

Start the Vite development server:

```bash
npm run dev
```

The frontend will normally be available at:

```text
http://localhost:5173
```

---

# 🐳 Docker Setup

BlueBank uses Docker Compose for the production deployment.

The application consists of four services:

```text
api
worker
frontend
caddy
```

---

## Docker Services

### API

Flask backend running with Gunicorn.

```text
api:5000
```

### Worker

Runs scheduled transfers:

```bash
python scheduled_transfer_worker.py
```

### Frontend

Serves the React application:

```text
frontend:80
```

### Caddy

Handles:

- HTTPS
- SSL certificates
- Reverse proxy
- Frontend routing
- API routing

---

# 🔐 Environment Configuration

Create the production environment file:

```bash
cp .env.example .env
```

Example configuration:

```env
APP_DOMAIN=bluebank-demo.duckdns.org

FRONTEND_ORIGINS=https://bluebank-demo.duckdns.org

FLASK_SECRET_KEY=<your-secret-key>

FLASK_DEBUG=false

SESSION_COOKIE_SECURE=true

SESSION_COOKIE_SAMESITE=Lax

SCHEDULED_TRANSFER_POLL_SECONDS=15

MONGO_URI=<your-mongodb-atlas-uri>

BANK_STAFF_USERS='[{"username":"admin","password_hash":"<werkzeug-password-hash>","role":"admin"}]'
```

### Environment Variables

| Variable | Purpose |
|---|---|
| `APP_DOMAIN` | Production domain |
| `FRONTEND_ORIGINS` | Allowed frontend origin |
| `FLASK_SECRET_KEY` | Flask session security |
| `FLASK_DEBUG` | Flask debug mode |
| `SESSION_COOKIE_SECURE` | Secure session cookies |
| `SESSION_COOKIE_SAMESITE` | Session cookie policy |
| `SCHEDULED_TRANSFER_POLL_SECONDS` | Worker polling interval |
| `MONGO_URI` | MongoDB Atlas connection |
| `BANK_STAFF_USERS` | Staff/admin authentication |

> Never commit `.env` to GitHub.

---

# ☁️ AWS EC2 Deployment

## 1. Launch EC2

Launch an EC2 instance using:

```text
Amazon Linux 2023
```

Connect using:

```bash
ssh -o IdentitiesOnly=yes -i <your-key.pem> ec2-user@<EC2_PUBLIC_IP>
```

---

## 2. Configure Security Group

Allow:

| Port | Protocol | Source |
|---|---|---|
| 22 | TCP | My IP |
| 80 | TCP | Anywhere |
| 443 | TCP | Anywhere |

Do **not** expose:

```text
5000
27017
```

---

## 3. Install Docker

```bash
sudo dnf update -y
sudo dnf install -y docker
```

Start Docker:

```bash
sudo systemctl enable --now docker
```

Add the current user to the Docker group:

```bash
sudo usermod -aG docker ec2-user
```

Reconnect to EC2.

Verify:

```bash
docker --version
docker ps
```

---

## 4. Install Git

```bash
sudo dnf install -y git
```

Verify:

```bash
git --version
```

---

## 5. Clone the Repository

```bash
git clone https://github.com/Survendra/bank_management_system.git
cd bank_management_system
```

---

# 🐳 Docker Compose Deployment

Verify the Compose configuration:

```bash
docker compose config
```

Build the frontend:

```bash
docker compose build frontend
```

Build the backend and worker:

```bash
docker compose build api worker
```

Or build everything:

```bash
docker compose build
```

Start the application:

```bash
docker compose up -d
```

Start the worker:

```bash
docker compose up -d worker
```

Check all services:

```bash
docker compose ps
```

Expected:

```text
api        Up (healthy)
worker     Up
frontend   Up
caddy      Up
```

---

# 🌍 DuckDNS Configuration

The production domain is:

```text
bluebank-demo.duckdns.org
```

The DuckDNS record points to the EC2 public IP.

```text
bluebank-demo.duckdns.org
            |
            v
       EC2 Public IP
            |
            v
         AWS EC2
```

---

# 🔒 Caddy HTTPS Configuration

The production Caddyfile is:

```caddyfile
{$APP_DOMAIN} {
    encode zstd gzip

    handle /api/* {
        reverse_proxy api:5000
    }

    handle {
        reverse_proxy frontend:80
    }
}
```

This provides two important routes.

### API

```text
/api/*
    ↓
api:5000
```

### Frontend

```text
/*
    ↓
frontend:80
```

Caddy automatically manages HTTPS certificates for the configured domain.

---

# 🩺 Health Check

BlueBank provides an API health endpoint:

```text
/api/health
```

Test locally through Caddy:

```bash
curl http://localhost/api/health
```

Test the production API:

```bash
curl https://bluebank-demo.duckdns.org/api/health
```

Expected:

```json
{
    "message": "Bank API is running",
    "success": true
}
```

---

# 🌐 Production Application

Open:

**https://bluebank-demo.duckdns.org**

The frontend communicates with the Flask API through Caddy.

---

# 🔄 Updating the Application

After making changes and pushing them to GitHub:

```bash
cd ~/bank_management_system
git pull
```

Rebuild:

```bash
docker compose build
```

Deploy:

```bash
docker compose up -d
```

Ensure the worker is running:

```bash
docker compose up -d worker
```

Verify:

```bash
docker compose ps
```

Test:

```bash
curl https://bluebank-demo.duckdns.org/api/health
```

---

# 📋 Useful Docker Commands

### Check services

```bash
docker compose ps
```

### Start services

```bash
docker compose up -d
```

### Stop services

```bash
docker compose down
```

### Restart API

```bash
docker compose restart api
```

### Restart frontend

```bash
docker compose restart frontend
```

### Restart worker

```bash
docker compose restart worker
```

### Restart Caddy

```bash
docker compose restart caddy
```

### API logs

```bash
docker compose logs api
```

### Follow API logs

```bash
docker compose logs -f api
```

### Worker logs

```bash
docker compose logs -f worker
```

### Caddy logs

```bash
docker compose logs -f caddy
```

### Frontend logs

```bash
docker compose logs -f frontend
```

---

# 🔧 Troubleshooting

## API is unhealthy

Check:

```bash
docker compose ps
```

Then:

```bash
docker compose logs api
```

Check MongoDB Atlas network access if you see:

```text
ServerSelectionTimeoutError
```

Find the EC2 public IP:

```bash
curl -4 https://ifconfig.me
```

Add the IP to MongoDB Atlas Network Access.

Then restart:

```bash
docker compose restart api
```

---

## API works internally but not through the domain

Check the Caddyfile:

```bash
cat deploy/aws/Caddyfile
```

Make sure it contains:

```caddyfile
handle /api/* {
    reverse_proxy api:5000
}
```

Restart Caddy:

```bash
docker compose up -d caddy
```

Test:

```bash
curl https://bluebank-demo.duckdns.org/api/health
```

---

## HTTPS is not working

Check:

```bash
docker compose logs caddy
```

Verify:

- DuckDNS points to EC2
- Port 80 is open
- Port 443 is open
- `APP_DOMAIN` is correct
- Caddy is running

---

## Worker is not running

Check:

```bash
docker compose ps
```

Start it:

```bash
docker compose up -d worker
```

View logs:

```bash
docker compose logs -f worker
```

---

# 🔐 Security

The application uses several security mechanisms:

- PBKDF2-SHA256 PIN hashing
- Salted password/PIN storage
- Login attempt limits
- Temporary account lockout
- 2FA
- Secure session cookies
- HTTPS
- Flask secret key
- MongoDB Atlas network restrictions
- Environment-based secrets
- No direct public exposure of Flask port 5000
- No direct public exposure of MongoDB port 27017

---

# 🚫 Production Security Notes

BlueBank is an educational banking project.

Do not use this application for:

- Real bank accounts
- Real financial transactions
- Real payment processing
- Production banking infrastructure
- Storing real customer financial information

The application should only use synthetic/demo data.

---

# 📊 Production Architecture Summary

```text
React + Vite
     |
     v
Caddy
     |
     +--------------------+
     |                    |
     v                    v
Flask API              Frontend
Gunicorn               Nginx
     |
     v
MongoDB Atlas
     ^
     |
Scheduled Transfer Worker
```

---

# ✅ Deployment Checklist

## AWS

- [x] EC2 instance created
- [x] Amazon Linux 2023 installed
- [x] Docker installed
- [x] Git installed
- [x] Security group configured

## Application

- [x] Repository cloned
- [x] `.env` configured
- [x] Backend container built
- [x] Frontend container built
- [x] Worker configured
- [x] Docker Compose configured

## Database

- [x] MongoDB Atlas configured
- [x] EC2 IP allowed in Atlas
- [x] Database connection verified

## Networking

- [x] DuckDNS configured
- [x] Domain points to EC2
- [x] Port 80 configured
- [x] Port 443 configured
- [x] Port 5000 not publicly exposed
- [x] Port 27017 not publicly exposed

## HTTPS

- [x] Caddy configured
- [x] HTTPS enabled
- [x] API routing configured
- [x] Frontend routing configured

## Final Verification

```bash
docker compose ps
```

Expected:

```text
api        Up (healthy)
worker     Up
frontend   Up
caddy      Up
```

Health check:

```bash
curl https://bluebank-demo.duckdns.org/api/health
```

Expected:

```json
{
    "message": "Bank API is running",
    "success": true
}
```

---

# 🎯 Project Status

BlueBank is successfully deployed using:

```text
AWS EC2
    +
Docker
    +
Docker Compose
    +
Caddy
    +
React/Vite
    +
Flask/Gunicorn
    +
MongoDB Atlas
    +
DuckDNS
    +
HTTPS
```

**Live Application:**  
https://bluebank-demo.duckdns.org

**Status:** 🟢 Deployed and operational
