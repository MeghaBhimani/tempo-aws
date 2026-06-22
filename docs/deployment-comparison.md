# Backend Deployment Comparison: EC2 vs ECS Fargate vs Lambda

All three options run the same Flask `app.py` with no code changes (except the Lambda handler). This document compares them across the dimensions that matter for a production music app.

## Side-by-Side Summary

| Factor | EC2 | ECS Fargate | Lambda + API Gateway |
|--------|-----|-------------|----------------------|
| **Setup complexity** | Low | Medium | Medium |
| **Cost model** | Per hour (always on) | Per hour (task running) | Per request (pay per call) |
| **Free tier** | 750 hrs/month (t2.micro) | None | 1M requests/month |
| **Cold start** | None | ~30s (first task start) | ~1–2s (after idle) |
| **Max request time** | Unlimited | Unlimited | 15 minutes |
| **Auto-scaling** | Manual (or Auto Scaling group) | Built-in (ECS Service) | Automatic (up to 1000 concurrent) |
| **Binary responses** | Native | Native | Requires base64 encoding |
| **SSH / debugging** | Direct SSH access | CloudWatch Logs only | CloudWatch Logs only |
| **Persistent state** | Can write to disk | Ephemeral (container) | Ephemeral (/tmp only) |
| **Managed infra** | You manage OS, patches | AWS manages host OS | Fully managed |
| **Best for** | Dev / prototyping | Production containers | Spiky / low-traffic workloads |

---

## EC2

**How it works:** Flask runs as a gunicorn process directly on a virtual machine. You SSH in, pull code from GitHub, and restart gunicorn.

**Pros:**
- Simplest setup — no Docker, no packaging
- Full control: can install anything, inspect logs directly, edit files in place
- Persistent disk — can store files locally if needed
- No cold starts

**Cons:**
- You manage OS updates, security patches, and restarts
- IP address changes when instance restarts (AWS Academy limitation)
- No automatic scaling — one instance handles all traffic
- Instance runs 24/7 even with zero traffic

**Suitable when:** Prototyping, learning, or running a low-traffic internal tool where downtime is acceptable.

---

## ECS Fargate

**How it works:** Flask runs inside a Docker container. AWS manages the underlying host. An Application Load Balancer provides a stable DNS name and distributes traffic across tasks.

**Pros:**
- Stable URL via ALB — survives lab restarts without IP changes
- Auto-scaling: ECS can add more tasks under load
- No server management — AWS patches the host OS
- Rolling deployments: new image deploys without downtime
- Same Docker image works locally and in production

**Cons:**
- Requires Docker knowledge and an ECR repository
- Slightly higher setup effort (cluster, task definition, ALB, security groups)
- Task must be running to serve requests — minimum ~$10/month for one Fargate task
- Longer deploy cycle: build image → push to ECR → force redeploy

**Suitable when:** Running a containerised app in production that needs reliability, a stable URL, and horizontal scaling.

---

## Lambda + API Gateway

**How it works:** Flask is packaged as a ZIP file and invoked per HTTP request. API Gateway translates HTTP requests into Lambda events using the `aws-wsgi` adapter.

**Pros:**
- True pay-per-request — costs near zero for low traffic
- Fully managed: no servers, no containers, no patching
- Scales instantly to thousands of concurrent requests
- No infrastructure to maintain between deployments

**Cons:**
- Cold start: first request after idle takes ~1–2 seconds
- Binary responses (images) require base64 encoding — adds complexity
- 15-minute maximum execution time per invocation
- Stateless: no persistent disk, no background threads
- API Gateway v2 (HTTP API) uses payload format v2 — must set integration to v1 for `aws-wsgi` compatibility
- Harder to debug: no SSH, logs only in CloudWatch

**Suitable when:** The API has variable or unpredictable traffic, you want zero infrastructure overhead, or you need to minimise cost on a low-traffic app.

---

## Recommendation for This App

| Scenario | Recommended option |
|----------|--------------------|
| Assignment / prototype | **EC2** — fastest to set up and iterate |
| Production with steady traffic | **ECS Fargate** — stable URL, auto-scaling, no cold starts |
| Production with low / spiky traffic | **Lambda** — cheapest, zero maintenance |

For Tempo specifically, **ECS Fargate** is the strongest production choice because:
- The image proxy (`/api/image`) streams binary data — no base64 complexity
- Music searches can be slow (DynamoDB scan) — no cold-start penalty
- ALB provides a stable HTTPS-ready URL without IP changes
