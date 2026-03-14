# ReAgent Deployment Guide

This guide covers every supported way to deploy the ReAgent server, from local
development to production Kubernetes clusters.

---

## 1. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.9+ | 3.12 recommended |
| pip | latest | or any PEP-517 compatible installer |
| Docker | 20.10+ | optional, for containerised deployments |
| Helm | 3.x | optional, for Kubernetes deployments |

---

## 2. Local Development

```bash
# Install ReAgent with server extras
pip install -e ".[server]"

# Start the server (defaults to 0.0.0.0:8080)
reagent server start

# Override host/port
reagent server start --host 127.0.0.1 --port 9090

# Verify
curl http://localhost:8080/health
# {"status":"ok"}
```

The server stores data in a local SQLite database (default
`reagent_server.db` in the working directory). Override the path with
`--db /path/to/data.db` or the `REAGENT_SERVER_DB` environment variable.

---

## 3. Docker Deployment

### 3.1 Building the Image

```bash
docker build -t reagent-server:latest .
```

The multi-stage `Dockerfile` produces a slim image that runs as a non-root
`reagent` user (UID 1000).

### 3.2 Running with `docker run`

```bash
docker run -d \
  --name reagent \
  -p 8080:8080 \
  -v reagent-data:/data \
  -e REAGENT_API_KEYS="rk-my-secret-key" \
  reagent-server:latest
```

### 3.3 Using Docker Compose

The repository ships a `docker-compose.yml` that bundles the server with a
Caddy reverse proxy for automatic TLS.

```bash
# Set your API key(s)
export REAGENT_API_KEYS="rk-abc,rk-xyz"

# Start everything
docker compose up -d

# Tail logs
docker compose logs -f reagent-server
```

Services defined in `docker-compose.yml`:

| Service | Port | Description |
|---------|------|-------------|
| `reagent-server` | 8080 | Core API server |
| `caddy` | 80 / 443 | Reverse proxy with automatic HTTPS |

### 3.4 Persistent Storage

The Docker image declares a `/data` volume. The SQLite database is stored at
`/data/reagent.db` by default. Map a named volume or host directory to
`/data` so data survives container recreation:

```bash
# Named volume (recommended)
docker run -v reagent-data:/data reagent-server:latest

# Host directory
docker run -v /srv/reagent:/data reagent-server:latest
```

### 3.5 Setting API Keys

Pass a comma-separated list of valid keys via the `REAGENT_API_KEYS`
environment variable. When no keys are configured, the server runs in
**dev mode** (no authentication required).

```bash
docker run -e REAGENT_API_KEYS="rk-key1,rk-key2" reagent-server:latest
```

---

## 4. Kubernetes Deployment

### 4.1 Helm Chart

A Helm chart is included at `deploy/helm/reagent-server/`.

```bash
helm install reagent ./deploy/helm/reagent-server
```

### 4.2 Configuring Values

Key values in `values.yaml`:

| Value | Default | Description |
|-------|---------|-------------|
| `image.repository` | `reagent-server` | Container image name |
| `image.tag` | `latest` | Image tag |
| `replicas` | `1` | Number of pods |
| `port` | `8080` | Container port |
| `persistence.enabled` | `true` | Create a PVC for SQLite data |
| `persistence.size` | `10Gi` | PVC size |
| `persistence.storageClass` | `""` | Storage class (empty = cluster default) |
| `apiKeys` | `""` | Comma-separated API keys |
| `ingress.enabled` | `false` | Create an Ingress resource |
| `ingress.host` | `reagent.example.com` | Ingress hostname |
| `resources.requests.memory` | `256Mi` | Memory request |
| `resources.limits.memory` | `512Mi` | Memory limit |

### 4.3 Example with Custom Values

```bash
helm install reagent ./deploy/helm/reagent-server \
  --set image.repository=ghcr.io/myorg/reagent-server \
  --set image.tag=v0.1.0 \
  --set persistence.size=50Gi \
  --set persistence.storageClass=gp3 \
  --set apiKeys="rk-prod-key-1\,rk-prod-key-2" \
  --set ingress.enabled=true \
  --set ingress.host=reagent.mycompany.com
```

---

## 5. Cloud Deployment Examples

### 5.1 AWS (ECS Fargate)

```bash
# Build and push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
docker tag reagent-server:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/reagent-server:latest
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/reagent-server:latest

# Create service (assumes task definition & cluster exist)
aws ecs create-service \
  --cluster reagent \
  --service-name reagent-server \
  --task-definition reagent-server:1 \
  --desired-count 1 \
  --launch-type FARGATE
```

> **Note:** For persistent SQLite storage on Fargate, mount an EFS volume to
> `/data` in your task definition.

### 5.2 GCP (Cloud Run)

```bash
# Build with Cloud Build
gcloud builds submit --tag gcr.io/my-project/reagent-server

# Deploy
gcloud run deploy reagent-server \
  --image gcr.io/my-project/reagent-server \
  --port 8080 \
  --set-env-vars "REAGENT_API_KEYS=rk-prod-key" \
  --allow-unauthenticated \
  --region us-central1
```

> **Note:** Cloud Run is stateless. Use Cloud SQL or mount a GCS FUSE volume
> for persistence if you need durable storage.

### 5.3 Azure (Container Apps)

```bash
az containerapp create \
  --name reagent-server \
  --resource-group reagent-rg \
  --environment reagent-env \
  --image ghcr.io/myorg/reagent-server:latest \
  --target-port 8080 \
  --ingress external \
  --env-vars "REAGENT_API_KEYS=rk-prod-key"
```

### 5.4 DigitalOcean (App Platform)

```bash
doctl apps create --spec - <<'EOF'
name: reagent-server
services:
  - name: server
    image:
      registry_type: DOCKER_HUB
      repository: myorg/reagent-server
      tag: latest
    http_port: 8080
    envs:
      - key: REAGENT_API_KEYS
        value: "rk-prod-key"
        type: SECRET
EOF
```

---

## 6. Reverse Proxy / TLS

### 6.1 Caddy

The repository includes a `Caddyfile` that is mounted into the Caddy container
by Docker Compose:

```
reagent.example.com {
    reverse_proxy reagent-server:8080
}
```

Replace `reagent.example.com` with your domain. Caddy handles TLS certificate
issuance and renewal automatically via Let's Encrypt.

### 6.2 Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name reagent.example.com;

    ssl_certificate     /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 7. Configuration Reference

### 7.1 Server Environment Variables

These control the server process itself.

| Variable | Default | Description |
|----------|---------|-------------|
| `REAGENT_SERVER_HOST` | `0.0.0.0` | Bind address |
| `REAGENT_SERVER_PORT` | `8080` | Bind port |
| `REAGENT_SERVER_DB` | `reagent_server.db` | Path to SQLite database file |
| `REAGENT_API_KEYS` | *(empty)* | Comma-separated list of valid API keys. Empty = no auth (dev mode) |

### 7.2 SDK / Client Environment Variables

These configure the ReAgent SDK when connecting to a remote server.

| Variable | Default | Description |
|----------|---------|-------------|
| `REAGENT_MODE` | `local` | `local` or `remote` |
| `REAGENT_SERVER_URL` | *(none)* | URL of the ReAgent server (e.g. `https://reagent.example.com`) |
| `REAGENT_API_KEY` | *(none)* | API key for authenticating with the server |
| `REAGENT_PROJECT` | *(none)* | Default project name attached to runs |
| `REAGENT_TRANSPORT_MODE` | *(default)* | Transport mode for sending events |
| `REAGENT_STORAGE_TYPE` | `jsonl` | Storage backend type for local mode |
| `REAGENT_STORAGE_PATH` | `~/.reagent/traces` | Path for local trace storage |
| `REAGENT_BUFFER_SIZE` | `10000` | In-memory event buffer size |
| `REAGENT_FLUSH_INTERVAL_MS` | `1000` | Buffer flush interval in milliseconds |
| `REAGENT_REDACTION_ENABLED` | `true` | Enable automatic PII redaction |
| `REAGENT_REDACTION_MODE` | *(default)* | Redaction engine mode |
| `REAGENT_REPLAY_MODE` | *(default)* | Default replay mode |
| `REAGENT_OUTPUT_FORMAT` | *(default)* | CLI output format |
| `REAGENT_COLOR` | `true` | Colour output in the CLI |
| `REAGENT_DEBUG` | `false` | Enable debug logging |
| `REAGENT_VERBOSE` | `false` | Enable verbose output |

---

## 8. Monitoring

### 8.1 Health Check Endpoint

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

A `200` response with `{"status":"ok"}` means the server is ready.

### 8.2 Docker HEALTHCHECK

The `Dockerfile` includes a built-in health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
```

Docker will automatically mark the container as `unhealthy` if the check fails
3 times in a row.

### 8.3 Kubernetes Probes

Add liveness and readiness probes to your deployment (the Helm chart configures
these by default):

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 3
  periodSeconds: 10
```

---

## 9. Backup & Recovery

### 9.1 SQLite Backup Strategies

**Option A: File copy while the server is stopped**

```bash
# Stop the server
docker compose stop reagent-server

# Copy the database
cp /data/reagent.db /backups/reagent-$(date +%Y%m%d).db

# Restart
docker compose start reagent-server
```

**Option B: Online backup with the `sqlite3` CLI**

```bash
sqlite3 /data/reagent.db ".backup /backups/reagent-$(date +%Y%m%d).db"
```

This is safe to run while the server is still handling requests.

### 9.2 Volume Snapshots

If running on a cloud provider with snapshot-capable block storage:

```bash
# AWS EBS example
aws ec2 create-snapshot --volume-id vol-0abc123 --description "reagent backup"

# GCP Persistent Disk example
gcloud compute disks snapshot reagent-data --zone us-central1-a
```

---

## 10. Security Considerations

1. **Always use TLS in production.** Place the server behind a reverse proxy
   (Caddy, Nginx, cloud load balancer) that terminates TLS. Never expose the
   server directly on the public internet over plain HTTP.

2. **Set API keys.** Without `REAGENT_API_KEYS`, the server runs in dev mode
   with no authentication. Always configure at least one key for any
   non-local deployment.

3. **Run as non-root.** The provided `Dockerfile` already creates and runs as
   the `reagent` user (UID 1000). Do not override this with `--user root`.

4. **Network isolation.** In Kubernetes or Docker, place the server in a
   private network. Only the reverse proxy or load balancer should be publicly
   accessible.

5. **Secrets management.** Avoid baking API keys into images. Use environment
   variables, Docker secrets, or Kubernetes Secrets to inject keys at
   runtime.

6. **Database access.** The SQLite file contains all trace data. Restrict file
   permissions on the volume mount to the `reagent` user only.
