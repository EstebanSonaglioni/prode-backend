# Backend for Prode

Django REST API for the Prode tournament prediction app.

## Tech Stack

- **Python 3.12**
- **Django 6** + Django REST Framework
- **PostgreSQL** (via Supabase in production / SQLite for local dev)
- **JWT Authentication** (djangorestframework-simplejwt)
- **File Storage** (Supabase Storage S3-compatible bucket)
- **Deployment** (Vercel Serverless)

## Live URL

- **API Base:** `https://prode-backend.vercel.app/`
- **Frontend:** [https://prode-frontend-drab.vercel.app/](https://prode-frontend-drab.vercel.app/)

## Running Locally

### 1. Create virtual environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Create a `.env` file in the `backend/` folder:

```env
DEBUG=True
SECRET_KEY=your-local-secret-key
DATABASE_URL=  # leave empty to use SQLite
CORS_ALLOWED_ORIGINS=http://localhost:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173
ENVIRONMENT=development
```

### 4. Run migrations & start server

```bash
python manage.py migrate
python manage.py runserver
```

The API will be available at `http://localhost:8000`.

---

## Running with Docker

### Build image

```bash
docker build -t prode-backend .
```

### Run container

```bash
docker run -p 8000:8000 --env-file .env prode-backend
```

The API will be available at `http://localhost:8000`.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` or `False` |
| `DATABASE_URL` | PostgreSQL connection string (optional, falls back to SQLite) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of allowed frontend origins |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins |
| `DEFAULT_FILE_STORAGE` | Set to `storages.backends.s3boto3.S3Boto3Storage` for Supabase |
| `AWS_S3_ENDPOINT_URL` | Supabase S3 endpoint |
| `AWS_STORAGE_BUCKET_NAME` | Supabase bucket name |
| `AWS_ACCESS_KEY_ID` | Supabase S3 access key |
| `AWS_SECRET_ACCESS_KEY` | Supabase S3 secret key |

## Project Structure

```
backend/
├── api/                 # Vercel serverless entry point
├── core/                # Django settings, WSGI, custom storage backend
├── media/               # Image upload models & views
├── prode/               # Tournaments, matches, predictions, teams
├── users/               # Custom user model, auth views
├── manage.py
├── requirements.txt
└── vercel.json
```
