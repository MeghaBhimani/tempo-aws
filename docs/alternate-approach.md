# Recommended Production Architecture

This document describes the alternate approaches for the Tempo cloud based music application.

---

## Current Constraints and Why They Exist

| Concern | Current Solution | Constraint |
|---------|-----------------|------------|
| Frontend hosting | S3 static website (HTTP) | AWS Academy blocks CloudFront and ACM certificates |
| Image serving | Flask `/api/image` proxy | Account-level SCP blocks public S3 bucket policies |
| Auth | sessionStorage (no cookies) | HTTP frontend + HTTPS API triggers mixed content block; SameSite cookie restrictions |

---

## Recommended Changes

### 1. AWS Amplify for Frontend Hosting

Replace the S3 static website with **AWS Amplify Hosting**:

```
GitHub (main branch) → Amplify auto-deploy → HTTPS CDN → Browser
```

| | S3 Website (current) | Amplify |
|--|--|--|
| HTTPS | No (HTTP only) | Yes (automatic, free ACM cert) |
| Auto-deploy on git push | No — manual S3 upload | Yes |
| CDN | No | Yes (CloudFront under the hood) |
| Custom domain | Manual Route 53 setup | Built-in |
| Cost | Near zero | Free tier: 5 GB storage, 15 GB bandwidth/month |

**Why this matters:** The current HTTP frontend cannot make fetch calls to HTTPS API endpoints (mixed content policy). Amplify gives HTTPS automatically, which also unlocks secure cookie-based auth.

---

### 2. CloudFront + S3 OAC to Replace the Flask Image Proxy

The Flask `/api/image` proxy exists because the S3 bucket cannot be made public (Academy SCP). In production, CloudFront with Origin Access Control (OAC) solves this properly:

```
Browser → CloudFront (HTTPS) → S3 private bucket (OAC) → artwork/
```

**Why this is better than the proxy:**
- Images are served from a CDN edge location — faster globally
- No compute cost (no EC2/Lambda processing each image request)
- No base64 encoding complexity for Lambda binary responses
- S3 bucket stays fully private — OAC grants CloudFront-only access

The Flask `/api/image` endpoint and `_image_url()` helper can be removed entirely.

---

### 3. Secure Auth with HTTPS Cookies

With Amplify providing HTTPS on the frontend:
- Replace `sessionStorage` with Flask server-side sessions
- Set `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_SAMESITE=Lax`, `SESSION_COOKIE_HTTPONLY=True`
- Auth state survives page refresh without re-login
- `HttpOnly` flag prevents JavaScript from reading the session cookie (XSS protection)

```python
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
)
```

---

## Summary of Changes

| Current | Recommended | Benefit |
|---------|-------------|---------|
| HTTP S3 static website | AWS Amplify (HTTPS, auto-deploy) | HTTPS, no manual uploads, CDN |
| Flask `/api/image` proxy | CloudFront OAC → S3 direct | Faster images, no compute cost |
| sessionStorage auth | HTTPS session cookies | Survives refresh, XSS protection |

The core `app.py` Flask routes and DynamoDB schema remain unchanged. All improvements are at the infrastructure and configuration layer.
