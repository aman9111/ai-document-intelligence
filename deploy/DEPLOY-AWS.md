# Deploy to AWS (EC2)

This puts the whole app (database, backend, frontend) on one small AWS server with a free
domain and HTTPS. It uses the same `docker-compose.yml` as local development, plus
`docker-compose.prod.yml`, which adds [Caddy](https://caddyserver.com) for HTTPS.

```
Internet ──▶ Caddy (80/443, HTTPS) ──▶ frontend (nginx) ──▶ /api ──▶ backend ──▶ db (pgvector)
```

Only Caddy is reachable from the internet. The database and backend are only reachable
inside Docker.

## What it costs

Checked in September 2026. AWS changes its offers, so check the current terms when you sign up.

| Item | Cost | Paid by |
|---|---|---|
| Server `t4g.small` (2 vCPU, 2 GB RAM, ARM) | $0: free trial of 750 hours a month until 31 Dec 2026 | AWS free trial |
| 30 GB disk (EBS gp3) | about $2.40 a month | free credits |
| Public IPv4 address | about $3.60 a month | free credits |

New accounts on the **Free plan** get $100 of credits (up to $200 after a few onboarding
tasks) for 6 months. On the Free plan AWS does not charge your card: when the credits
or the 6 months run out, the account is closed unless you upgrade to the Paid plan.
**Don't upgrade unless you want to pay.**

## 1. Create the AWS account

1. Go to https://aws.amazon.com/free/ and click **Create a Free Account**.
2. Choose the **Free plan**. Indian cards (Visa, Mastercard, RuPay, Amex) are accepted. A
   small temporary charge may appear for verification and is refunded.
3. After signing in, turn on **MFA** for the root user: account menu (top right) →
   **Security credentials** → **Assign MFA device**.

## 2. Add a budget alert

So you get an email as soon as anything starts to cost money. This is also one of the
onboarding tasks that adds free credits.

1. Search for **Budgets** in the top search bar → **Create budget**.
2. Choose the **Zero spend budget** template (or a monthly budget of $5).
3. Enter your email and create it.

## 3. Pick the region

In the top-right corner, choose **Asia Pacific (Mumbai) ap-south-1** (or the region
closest to you). Everything below must be created in the same region.

## 4. Create an SSH key

**EC2 → Network & Security → Key Pairs → Create key pair**

- Name: `ai-docs-key`
- Type: `ED25519`, format: `.pem`

The file downloads once. Move it and lock it down:

```bash
mv ~/Downloads/ai-docs-key.pem ~/.ssh/
chmod 400 ~/.ssh/ai-docs-key.pem
```

## 5. Launch the server

**EC2 → Instances → Launch instances**

| Setting | Value |
|---|---|
| Name | `ai-document-intelligence` |
| AMI | **Ubuntu Server 24.04 LTS**, architecture **64-bit (Arm)** |
| Instance type | **t4g.small** |
| Key pair | `ai-docs-key` |
| Network settings → Firewall (security group) | Create a new one and tick: **Allow SSH traffic from My IP**, **Allow HTTPS traffic from the internet**, **Allow HTTP traffic from the internet** |
| Storage | **30 GiB gp3** |

Click **Launch instance**.

> Pick `64-bit (Arm)` with `t4g`. An x86 image won't offer `t4g` types.

## 6. Give the server a fixed IP address

Without this the IP changes every time the server is stopped and started.

1. **EC2 → Network & Security → Elastic IPs → Allocate Elastic IP address → Allocate**
2. Select it → **Actions → Associate Elastic IP address** → choose the instance → **Associate**
3. Note the IP address.

## 7. Get a free domain

1. Sign in at https://www.duckdns.org.
2. Add a subdomain, for example `mydocs` → `mydocs.duckdns.org`.
3. Set **current ip** to the Elastic IP and click **update ip**.

Any other domain works too: point an `A` record at the Elastic IP.

## 8. Set up the server

```bash
ssh -i ~/.ssh/ai-docs-key.pem ubuntu@<elastic-ip>

git clone https://github.com/aman9111/ai-document-intelligence.git
cd ai-document-intelligence
bash deploy/setup-server.sh
exit
```

The script installs Docker and adds 4 GB of swap, which the 2 GB server needs while it
builds the images. Log in again so `docker` works without `sudo`:

```bash
ssh -i ~/.ssh/ai-docs-key.pem ubuntu@<elastic-ip>
cd ai-document-intelligence
```

## 9. Configure

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # use for SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # use for POSTGRES_PASSWORD
nano .env
```

Fill in (save with `Ctrl+O`, `Enter`, exit with `Ctrl+X`):

```
POSTGRES_PASSWORD=<random>
SECRET_KEY=<random>
LLM_API_KEY=<a Groq key made just for this server>
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
DOMAIN=mydocs.duckdns.org
ALLOW_REGISTRATION=true
```

## 10. Start

```bash
docker compose up -d --build
docker compose ps              # all services should be "running" / "healthy"
docker compose logs -f caddy   # watch the HTTPS certificate being issued, Ctrl+C to stop
```

The first build takes 15–30 minutes on the small server. Then open **https://mydocs.duckdns.org**.

## 11. Close registration

Register your own account first, then stop strangers from signing up:

```bash
sed -i 's/^ALLOW_REGISTRATION=.*/ALLOW_REGISTRATION=false/' .env
docker compose up -d
```

## Everyday tasks

| Task | Command |
|---|---|
| Update to the latest code | `git pull && docker compose up -d --build` |
| See logs | `docker compose logs -f backend` |
| Restart | `docker compose restart` |
| Stop the app (data is kept) | `docker compose down` |
| Back up database + uploads | `bash deploy/backup.sh` |
| Copy backups to your computer | `scp -r -i ~/.ssh/ai-docs-key.pem ubuntu@<elastic-ip>:ai-document-intelligence/backups .` |
| See remaining credits | AWS console → **Billing and Cost Management → Credits** |

Keep backups **off the server**. If the instance is terminated, its disk goes with it.

## When you're done: remove everything

So nothing keeps using credits:

1. **EC2 → Instances** → select the instance → **Instance state → Terminate**
2. **EC2 → Elastic IPs** → select the IP → **Actions → Release** (an unattached IP is still billed)
3. **EC2 → Volumes** and **Snapshots**: delete anything left over

## Troubleshooting

| Problem | Check |
|---|---|
| `ssh` times out | Security group allows SSH from **your current IP** (it changes on a new Wi-Fi): EC2 → Security Groups → edit inbound rules |
| Site doesn't open | Security group allows HTTP 80 and HTTPS 443 from `0.0.0.0/0` |
| Certificate error / Caddy logs mention ACME | DuckDNS IP matches the Elastic IP (`ping mydocs.duckdns.org`), and port 80 is open |
| Build stops with "killed" | Not enough memory: check swap with `free -h` (the setup script adds 4 GB) |
| Ask AI says the AI isn't configured | `LLM_API_KEY` in `.env`, then `docker compose up -d` |
| "Registration is closed" | `ALLOW_REGISTRATION=false` is set: change it to `true` temporarily |

## Privacy

This is a learning project. Don't upload real medical records to a public server: the
text of relevant pages is sent to the LLM provider, and the app has no rate limiting,
audit logs or encryption at rest.
