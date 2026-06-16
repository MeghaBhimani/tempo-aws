# Tempo — Cloud Music App

A full-stack music subscription app built on AWS. Users can register, search a music catalogue, and subscribe to tracks. Deployable on EC2, ECS Fargate, or Lambda + API Gateway.

## Features

- User registration and login with bcrypt password hashing
- Music search by artist, title, album, or year
- Subscribe and unsubscribe to tracks
- Album artwork stored in private S3 bucket, served via Flask image proxy
- Stateless REST API — auth via sessionStorage (no server-side sessions)
- CORS-enabled for S3-hosted frontend

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, Flask, gunicorn |
| Database | AWS DynamoDB (Login, Music, Subscription tables) |
| Storage | AWS S3 — static frontend + private artwork bucket |
| Image serving | Flask `/api/image` proxy (avoids presigned URLs) |
| Auth | sessionStorage + bcrypt password hashing |
| Deployment | EC2 / ECS Fargate / Lambda + API Gateway |

## Project Structure

```
tempo-aws/
├── app.py                 # Flask REST API
├── Dockerfile             # Container definition for ECS deployment
├── requirements.txt
├── .env.example           # Environment variable template
├── frontend/
│   ├── login.html
│   ├── register.html
│   └── main.html
└── backend/
    ├── LoginCreateTable.java
    ├── MusicCreateTable.java
    ├── SubscriptionCreateTable.java
    └── load_music_data.py  # Fetches iTunes data, uploads artwork to S3, loads DynamoDB
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `FLASK_SECRET` | Flask secret key |
| `S3_BUCKET` | S3 bucket name for artwork (private) |
| `API_ORIGIN` | Public URL of the API (EC2, ALB, or API Gateway) |
| `ALLOWED_ORIGIN` | S3 website URL for CORS |
| `AWS_REGION` | AWS region (default: us-east-1) |

```bash
cp .env.example .env
# Fill in your values
```

## Setup

**Prerequisites:** Python 3.11+, AWS CLI configured, DynamoDB tables created.

```bash
# Install dependencies
pip install -r requirements.txt

# Load music catalogue (fetches from iTunes, uploads artwork to S3)
python backend/load_music_data.py

# Run locally
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/register` | Create account |
| POST | `/api/login` | Login |
| GET | `/api/query` | Search music (title, artist, year, album) |
| GET | `/api/subscriptions?email=` | Get user subscriptions |
| POST | `/api/subscribe` | Subscribe to a track |
| DELETE | `/api/unsubscribe` | Unsubscribe from a track |
| GET | `/api/image?key=artwork/...` | Proxy S3 artwork image |
| GET | `/health` | Health check |

## Deployment

Three deployment options — all use the same Flask app and DynamoDB tables.

### EC2
Run Flask directly on an EC2 instance with gunicorn. Set environment variables in `.env`.

### ECS Fargate
Build Docker image → push to ECR → create ECS cluster and service → attach Application Load Balancer.

### Lambda + API Gateway
Package app with `aws-wsgi` → upload ZIP to Lambda → create HTTP API in API Gateway → set payload format to 1.0.

## Database Design

Three DynamoDB tables:

### Login
| Attribute | Type | Role |
|-----------|------|------|
| `email` | String | Partition key |
| `user_name` | String | Display name |
| `password` | String | bcrypt hash |

### Music
| Attribute | Type | Role |
|-----------|------|------|
| `artist` | String | Partition key |
| `title_album` | String | Sort key (`title#album`) |
| `title` | String | Song title |
| `album` | String | Album name |
| `year` | Number | Release year |
| `image_url` | String | S3 artwork URL |

The sort key is `title#album` rather than `title` alone because the dataset contains duplicate song titles across different albums by the same artist (e.g. live versions, re-releases). Using the composite key guarantees uniqueness.

### Subscription
| Attribute | Type | Role |
|-----------|------|------|
| `emailId` | String | Partition key (user email) |
| `title_album` | String | Sort key (`title#album`) |
| `title`, `artist`, `album`, `year`, `image_url` | String | Denormalised for fast reads |

Subscription data is denormalised — all display fields are stored at write time so the subscriptions page requires only one DynamoDB query with no joins.

## Architecture

```
Browser (S3 static website)
        │
        │  HTTPS
        ▼
┌───────────────────┐
│  EC2 / ALB+ECS /  │   ← three interchangeable deployment targets
│  API Gateway+Lambda│
└────────┬──────────┘
         │
    ┌────┴─────┐
    │  Flask   │
    │  app.py  │
    └────┬─────┘
         │
   ┌─────┴──────┐
   │  DynamoDB  │   Login · Music · Subscription
   └────────────┘
         │
   ┌─────┴──────┐
   │  S3 bucket │   tempo-artist-bucket (private)
   │  artwork/  │   served via /api/image proxy
   └────────────┘
```

All three deployment targets run the same `app.py` with no code changes. The only difference is how the process is started (gunicorn, ECS task, or Lambda handler) and where environment variables are injected.

## Why Flask Image Proxy?

Artwork is stored in a private S3 bucket. Rather than making the bucket public or using presigned URLs (which expire and cause broken images), the `/api/image` endpoint fetches the object from S3 internally and streams it to the browser. This gives permanent, stable image URLs while keeping the bucket private and avoiding any frontend logic to handle URL expiry.
