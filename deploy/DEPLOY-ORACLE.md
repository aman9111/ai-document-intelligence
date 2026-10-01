# Deploy to a free Oracle Cloud server

This puts the whole app (database, backend, frontend) on one Linux server with a free
domain and HTTPS. It uses the same `docker-compose.yml` as local development, plus
`docker-compose.prod.yml`, which adds [Caddy](https://caddyserver.com) for HTTPS.

```
Internet ──▶ Caddy (80/443, HTTPS) ──▶ frontend (nginx) ──▶ /api ──▶ backend ──▶ db (pgvector)
```

Only Caddy is reachable from the internet. The database and backend are only reachable
inside Docker.

> Oracle's free limits change without notice. In September 2026 the Always Free ARM
> allowance is 2 OCPUs and 12 GB RAM in total, which is plenty for this app (it uses
> about 1–2 GB). Check the current limits when you sign up.

## 1. Create the server

1. Sign up at https://www.oracle.com/cloud/free/. A card is needed for verification.
   Pick your **home region** carefully, it can't be changed later, and free ARM servers
   are only created there.
2. Make an SSH key on your own computer, if you don't have one:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/oracle_server
   ```
3. In the console: **Compute → Instances → Create instance**
   - **Image:** Canonical Ubuntu 24.04 (or 22.04)
   - **Shape:** Ampere `VM.Standard.A1.Flex`, 2 OCPU, 12 GB memory
   - **Networking:** keep "Assign a public IPv4 address" on
   - **SSH keys:** paste the contents of `~/.ssh/oracle_server.pub`
   - **Boot volume:** 50 GB is enough (up to 200 GB is free)

   If you get **"Out of capacity"**, try again later or pick another availability domain.
4. Note the server's **public IP address**.

## 2. Open ports 80 and 443 in Oracle Cloud

**Networking → Virtual cloud networks →** your VCN **→ Security Lists → Default Security List
→ Add Ingress Rules**, twice:

| Source CIDR | IP protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

(The server's own firewall is opened by the setup script in step 4.)

## 3. Get a free domain

1. Sign in at https://www.duckdns.org.
2. Add a subdomain, for example `mydocs` → `mydocs.duckdns.org`.
3. Set its **current ip** to the server's public IP and click **update ip**.

Any other domain works too: point an `A` record at the server's IP.

## 4. Set up the server

```bash
ssh -i ~/.ssh/oracle_server ubuntu@<server-ip>

git clone https://github.com/aman9111/ai-document-intelligence.git
cd ai-document-intelligence
bash deploy/setup-server.sh
exit
```

Log in again (so `docker` works without `sudo`):

```bash
ssh -i ~/.ssh/oracle_server ubuntu@<server-ip>
cd ai-document-intelligence
```

## 5. Configure

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # use for SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # use for POSTGRES_PASSWORD
nano .env
```

Fill in:

```
POSTGRES_PASSWORD=<random>
SECRET_KEY=<random>
LLM_API_KEY=<your Groq key; make a separate key for the server>
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
DOMAIN=mydocs.duckdns.org
ALLOW_REGISTRATION=true
```

## 6. Start

```bash
docker compose up -d --build
docker compose ps              # all services should be "running" / "healthy"
docker compose logs -f caddy   # watch the HTTPS certificate being issued, Ctrl+C to stop
```

The first build takes 10–20 minutes on the ARM server. Then open **https://mydocs.duckdns.org**.

## 7. Close registration

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
| Stop (data is kept) | `docker compose down` |
| Back up database + uploads | `bash deploy/backup.sh` |
| Copy backups to your computer | `scp -r -i ~/.ssh/oracle_server ubuntu@<server-ip>:ai-document-intelligence/backups .` |

Keep backups **off the server**. If the server is deleted, its disk goes with it.

## Troubleshooting

| Problem | Check |
|---|---|
| Site doesn't open at all | Step 2 ingress rules, and `sudo iptables -L INPUT -n` shows ports 80/443 as ACCEPT |
| Certificate error / Caddy logs mention ACME | DuckDNS IP matches the server IP (`ping mydocs.duckdns.org`), and port 80 is open |
| Build stops with "killed" | Not enough memory: check swap with `free -h` (the setup script adds 4 GB) |
| Ask AI says the AI isn't configured | `LLM_API_KEY` in `.env`, then `docker compose up -d` |
| "Registration is closed" | `ALLOW_REGISTRATION=false` is set: change it to `true` temporarily |

## Privacy

This is a learning project. Don't upload real medical records to a public server: the
text of relevant pages is sent to the LLM provider, and the app has no rate limiting,
audit logs or encryption at rest.
