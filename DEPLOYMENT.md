# AWS free-plan demo deployment

This deployment runs the React frontend, Flask API, and scheduled-transfer
worker on one EC2 instance. Caddy provides HTTPS, and MongoDB Atlas stores the
application data. Use synthetic data only: this project is an educational
demo, not a production banking or payment service.

AWS's Free account plan is for new AWS customers, lasts up to six months or
until its credits are exhausted, and suspends the account when it expires.
AWS says a payment method is not required for most new sign-ups, though it may
request one for identity verification. Existing AWS customers may not qualify.
Read the current [AWS Free Tier terms](https://aws.amazon.com/free/free-tier-faqs/)
before creating resources; do not upgrade to a paid plan if you must avoid
charges.

## 1. Create an EC2 instance

1. Sign up for the AWS **Free account plan** if eligible.
2. Launch a small Linux EC2 instance offered by the Free plan (for example,
   Ubuntu Server 24.04 LTS and `t3.micro`, if shown as eligible in your region).
   Keep the root volume small and check the Free Tier cost information before
   launching.
3. Create a security group with inbound rules:
   - SSH (22) from **My IP** only.
   - HTTP (80) and HTTPS (443) from anywhere.
   - Do not expose ports 5000 or 27017.
4. Save the SSH private key securely. Never commit it to GitHub.
5. Create a free DuckDNS hostname and point its A record at the instance's
   public IPv4 address. Caddy will request and renew the HTTPS certificate.
   If the instance is stopped and its public IP changes, update DuckDNS and
   MongoDB Atlas.

## 2. Configure MongoDB and secrets

1. Use a MongoDB Atlas replica-set cluster that supports transactions. The
   backend uses the `bluebank` database.
2. Create a database user with only the access needed for this demo. In Atlas
   Network Access, allow the EC2 instance's public IPv4 address as a `/32`;
   avoid `0.0.0.0/0`.
3. On the EC2 instance, clone the repository and prepare its environment:

   ```bash
   git clone https://github.com/Survendra/bank_management_system.git
   cd bank_management_system
   cp .env.example .env
   nano .env
   ```

4. Set `APP_DOMAIN` and `FRONTEND_ORIGINS` to the DuckDNS hostname and its
   HTTPS origin. Set `MONGO_URI` to the Atlas connection URI. Generate a
   `FLASK_SECRET_KEY` with `python3 -c "import secrets; print(secrets.token_hex(32))"`.
   Create `BANK_STAFF_USERS` with at least one admin username and Werkzeug
   password hash; never place a plaintext password in that variable.
5. Keep `.env`, the database URI, staff hashes, and the SSH key private.

Generate a staff password hash on your development machine without putting
the plaintext password in shell history:

```powershell
cd backend
.\venv\Scripts\python.exe -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass()))"
```

## 3. Install Docker and start the app

On Ubuntu, install Docker and Compose, then add your user to the Docker group:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Reconnect over SSH so the group change takes effect. From the repository
directory, build and start the services:

```bash
docker compose build frontend
docker compose build api worker
docker compose up -d
docker compose ps
docker compose logs -f api worker caddy
```

The frontend and API share one HTTPS origin, so session cookies remain
first-party. The worker runs separately and processes due scheduled transfers
while the EC2 instance is running.

Check `https://your-subdomain.duckdns.org/api/health`, then test customer and
staff sign-in, a transfer, and a scheduled transfer using synthetic accounts.
To update later, run `git pull`, rebuild the frontend and backend images, and
run `docker compose up -d`.

AWS Free plan credits are temporary; EC2, storage, and networking consume
credits. Monitor the AWS account plan and usage, and do not rely on this setup
for continuous production service.
