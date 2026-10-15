# GCP Deployment Guide

This guide covers deploying Ghost Cursor to Google Cloud Platform.

---

## Prerequisites

```bash
# Install gcloud CLI
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login
gcloud auth application-default login

# Set your project
gcloud config set project ghost-cursor-project
gcloud config set compute/region us-central1
```

---

## 1. Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  vpcaccess.googleapis.com
```

---

## 2. Create GCP Resources

### Create a VPC Network

```bash
gcloud compute networks create ghost-cursor-vpc \
  --subnet-mode=custom

gcloud compute networks subnets create ghost-cursor-subnet \
  --network=ghost-cursor-vpc \
  --range=10.0.0.0/24 \
  --region=us-central1
```

### Create Cloud SQL PostgreSQL Instance

```bash
# Create instance
gcloud sql instances create ghost-cursor-db \
  --database-version=POSTGRES_17 \
  --tier=db-g1-small \
  --region=us-central1 \
  --availability-type=REGIONAL \
  --backup-location=us-central1 \
  --backup-start-time=02:00

# Create database
gcloud sql databases create ghost_cursor \
  --instance=ghost-cursor-db

# Create user
gcloud sql users create ghost_cursor_user \
  --instance=ghost-cursor-db \
  --password=$(openssl rand -base64 24)

# Get private IP
gcloud sql instances describe ghost-cursor-db \
  --format="value(ipAddresses.ipAddress)"
```

### Create Secret Manager Secrets

```bash
# API Keys
gcloud secrets create ghost-cursor-api-key \
  --replication-policy=automatic \
  --data-file=<(echo "your-random-api-key-here")

gcloud secrets create tenant-api-key-1 \
  --replication-policy=automatic \
  --data-file=<(echo "tenant-1-secret-key-here")

# Database credentials
DB_PASSWORD=$(openssl rand -base64 24)
gcloud secrets create db-password \
  --replication-policy=automatic \
  --data-file=<(echo "$DB_PASSWORD")
```

### Create Artifact Registry Repository

```bash
gcloud artifacts repositories create ghost-cursor-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="Ghost Cursor Docker images"
```

---

## 3. Build and Deploy Cloud Run

### Build Ghost Cursor Orchestrator

```bash
cd services/orchestrator

gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions=_IMAGE_NAME=ghost-cursor-api

# Or manually:
docker build -t us-central1-docker.pkg.dev/${PROJECT_ID}/ghost-cursor-repo/api:latest .
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/ghost-cursor-repo/api:latest
```

### Deploy Ghost Cursor API

```bash
gcloud run deploy ghost-cursor-api \
  --image=us-central1-docker.pkg.dev/${PROJECT_ID}/ghost-cursor-repo/api:latest \
  --region=us-central1 \
  --no-allow-unauthenticated \
  --service-account=ghost-cursor-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --add-cloudsql-instances=${PROJECT_ID}:us-central1:ghost-cursor-db \
  --set-secrets="DATABASE_URL=ghost-cursor-db-password:latest,GHOST_CURSOR_API_KEY=ghost-cursor-api-key:latest,TENANT_API_KEY_1=tenant-api-key-1:latest" \
  --min-instances=1 \
  --max-instances=5 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=5 \
  --timeout=60s
```

### Deploy ShopHive Demo App

```bash
cd demo/shophive

gcloud run deploy shophive-demo \
  --image=us-central1-docker.pkg.dev/${PROJECT_ID}/ghost-cursor-repo/demo:latest \
  --region=us-central1 \
  --no-allow-unauthenticated \
  --set-env-vars="GHOST_CURSOR_API_KEY=...,GHOST_CURSOR_TENANT_ID=shophive_demo,DATABASE_URL=postgresql://..." \
  --min-instances=1 \
  --max-instances=1
```

---

## 4. Set Up Ingress and Load Balancer

```bash
# Create external IP
gcloud compute addresses create ghost-cursor-ip \
  --network-tier=PREMIUM \
  --region=us-central1

# Create HTTPS load balancer
gcloud compute backend-services create ghost-cursor-backend \
  --protocol=HTTP2 \
  --health-checks=ghost-cursor-health \
  --region=us-central1

gcloud compute url-maps create ghost-cursor-url-map \
  --default-service=ghost-cursor-backend

gcloud compute target-https-proxies create ghost-cursor-https-proxy \
  --url-map=ghost-cursor-url-map \
  --ssl-certificates=ghost-cursor-cert

gcloud compute forwarding-rules create ghost-cursor-fr \
  --address=ghost-cursor-ip \
  --target-https-proxy=ghost-cursor-https-proxy \
  --ports=443 \
  --region=us-central1
```

---

## 5. Set Up Cloud Armor (Optional but Recommended)

```bash
gcloud compute security-policies create ghost-cursor-policy \
  --description="Ghost Cursor security policy"

# Add rate limiting rule
gcloud compute security-policies rules create 1000 \
  --security-policy=ghost-cursor-policy \
  --description="Rate limit" \
  --src-ip-range="*" \
  --action=deny-403 \
  --priority=1000 \
  --match="ip.src == *"
```

---

## 6. Deployment with Terraform

### `main.tf`

```hcl
provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "aiplatform.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
  ])
  service = each.key
}

resource "google_cloud_run_service" "ghost_cursor_api" {
  name     = "ghost-cursor-api"
  location = var.region

  template {
    spec {
      containers {
        image = var.api_image
        env {
          name  = "DATABASE_URL"
          value_from {
            secret_key_ref {
              name = "ghost-cursor-db-password"
              key  = "latest"
            }
          }
        }
      }
      container_concurrency = 5
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}
```

---

## 7. Monitoring and Logging

### Stackdriver Logging

```bash
# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ghost-cursor-api"
```

### Cloud Monitoring Dashboard

Create a dashboard for:
- Request count and latency
- Error rates
- Container CPU/Memory usage
- Database connection pool stats

---

## 8. Cost Optimization

### Recommended Settings

| Setting | Production | Development |
|---------|-----------|-------------|
| Min instances | 1 | 0 |
| Max instances | 5 | 2 |
| Memory | 512Mi | 256Mi |
| CPU | 1 vCPU | 0.5 vCPU |

### Cost Estimation

| Service | Monthly Cost (Production) |
|---------|--------------------------|
| Cloud Run (ghost-cursor-api) | ~$20-40 |
| Cloud Run (shophive-demo) | ~$10-20 |
| Cloud SQL PostgreSQL | ~$20-30 |
| Vertex AI (Gemini) | ~$10-50 |
| Cloud Storage | ~$5 |
| **Total** | **~$65-150** |

---

## 9. rollback

```bash
# Rollback to previous revision
gcloud run services update-traffic ghost-cursor-api \
  --to-revisions=ghost-cursor-api-00001=100

# Delete revision
gcloud run revisions delete ghost-cursor-api-00001 \
  --region=us-central1
```

---

## 10. Security Checklist

- [ ] API keys in Secret Manager (not env vars)
- [ ] Service account with minimal IAM permissions
- [ ] Cloud Armor security policy enabled
- [ ] HTTPS only (no HTTP)
- [ ] Private service connection to Cloud SQL
- [ ] VPC Service Controls applied
- [ ] Audit logging enabled
- [ ] Secret rotation scheduled

---

## 11. Troubleshooting

### Deployment fails with "Permission denied"

```bash
# Ensure service account has required permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:ghost-cursor-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:ghost-cursor-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### "Database connection failed"

```bash
# Check Cloud SQL is accessible
gcloud sql connect ghost-cursor-db \
  --user=ghost_cursor_user \
  --password=${DB_PASSWORD}

# Verify VPC connector is configured
gcloud compute networks vpc-access connectors list
```

### "Model not found"

```bash
# Verify Vertex AI is enabled
gcloud services list --enabled | grep aiplatform

# Check region supports the model
gcloud ai models list --region=us-central1
```