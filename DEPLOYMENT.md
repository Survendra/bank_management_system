# Demo deployment

This project is an educational banking demo, not a production banking or
payment service. Deploy it only with synthetic data; do not use real customer
financial or identity information.

The suggested deployment uses Vercel for the Vite frontend and Render for the
Flask API and scheduled-transfer worker. MongoDB Atlas must use a replica set
or compatible cluster because several operations require transactions.

## 1. Create the database

1. Create a MongoDB Atlas cluster and database user.
2. Set the database user's password and save the connection URI securely.
3. Allow the Render service's outbound IP addresses in Atlas Network Access.
   Avoid allowing connections from every IP address when possible.
4. The backend uses the `bluebank` database. Do not copy local `bank_data.json`
   or real account data to the hosted database.

## 2. Deploy the API and worker on Render

1. In Render, create a Blueprint from this GitHub repository and select
   `render.yaml`.
2. For the `bluebank-runtime` environment group, set:
   - `MONGO_URI` to the Atlas connection URI.
   - `BANK_STAFF_USERS` to a JSON array with at least one admin username,
     Werkzeug password hash, and `admin` role.
   - `FRONTEND_ORIGINS` temporarily to `https://your-project.vercel.app`.
     Replace it with the exact production Vercel origin after creating the
     frontend (no trailing slash).
3. Render generates `FLASK_SECRET_KEY`. Keep it private.
4. Wait for the API health check at `/api/health` and the scheduled-transfer
   worker to start.

Generate a staff password hash locally without putting the plaintext password
in shell history:

```powershell
cd backend
.\venv\Scripts\python.exe -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass()))"
```

Enter the hash, not the plaintext password, in Render's environment settings.
Never commit connection strings, hashes, or secret keys.

## 3. Deploy the frontend on Vercel

1. Import the same GitHub repository into Vercel.
2. Set the project **Root Directory** to `vite-project`, framework to Vite,
   build command to `npm run build`, and output directory to `dist`.
3. If Render assigned a different API URL, replace the hostname in
   `vite-project/vercel.json` with the actual Render URL.
4. Deploy the frontend, then replace the temporary `FRONTEND_ORIGINS` value
   in Render with the exact production Vercel origin and redeploy the API.
5. The Vercel rewrites proxy API, Swagger, and OpenAPI requests through the
   frontend origin so browser session cookies remain first-party.

The rewrite destination in `vite-project/vercel.json` assumes the Render API
URL is `https://bluebank-api.onrender.com`. If Render assigns a different URL,
replace that hostname in all three API/docs rewrite destinations and redeploy
the frontend.

After changing any environment variables, redeploy the affected service.
Verify customer login, staff login, a transfer using synthetic accounts, and a
scheduled transfer before sharing the demo.
