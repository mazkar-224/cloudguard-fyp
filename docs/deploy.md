# CloudGuard — Production Deployment Runbook (single EC2 + Docker Compose)

This is the step-by-step guide to run CloudGuard live on one AWS EC2 instance,
served over HTTPS by Caddy (automatic Let's Encrypt certificate).

**Architecture on the box:** one `docker-compose.prod.yml` stack —
`postgres` + `backend` (FastAPI/uvicorn) + `frontend` (nginx-served React SPA) +
`caddy` (reverse proxy / TLS). Caddy is the only thing exposed to the internet
(ports 80 + 443).

> ⚠️ **Money first.** A running EC2 instance bills continuously, whether or not
> anyone visits the site. **Set a billing alarm before you launch** (Step 0),
> and **tear everything down after your defense** (Teardown section). Consider
> only deploying in the final week before your viva.
>
> 💲 **No prices are quoted here on purpose.** AWS pricing changes by region,
> instance size, and over time. **Check the live AWS Pricing Calculator and the
> EC2 pricing page yourself** for your chosen size + region before you commit.

---

## Step 0 — Billing alarm (do this FIRST)

A CloudWatch billing alarm emails you if your estimated charges cross a small
threshold (e.g. $5). It is your safety net against a forgotten running instance.

**0a. Enable billing alerts (one-time, root user only):**
1. Sign in as the **root** account user.
2. Top-right account menu → **Billing and Cost Management** → **Billing preferences**.
3. Under **Alert preferences** → **Edit** → tick **Receive CloudWatch billing
   alerts** → **Save**.

**0b. Create the alarm:**
1. Switch region to **US East (N. Virginia) `us-east-1`** (billing metrics only
   publish there, regardless of where your instance runs).
2. **CloudWatch** → **Alarms** → **Create alarm** → **Select metric** →
   **Billing** → **Total Estimated Charge** → currency **USD** → **Select metric**.
3. Condition: **Static**, **Greater** than **5** (or 10) USD → **Next**.
4. Create a new SNS topic, enter your email, create the alarm.
5. **Confirm the SNS subscription** from the email AWS sends you — without that
   click, no alert is delivered.

---

## Step 1 — Launch the EC2 instance (Ubuntu LTS)

**Sizing.** This stack runs Postgres + a Python API + an nginx static server +
Caddy, and it also **builds the Docker images on the box**. The build (npm +
pip) is the memory-hungry part.
- **1 GB RAM is not enough** — the frontend `npm run build` can OOM-kill.
- A **2 vCPU / ~2 GB RAM** general-purpose instance (the `t3.small` class) is a
  comfortable, common choice for an FYP demo of this size.
- If you want to shave cost, you *can* try the next size down (~1 GB), but then
  **build the images elsewhere or add swap** (see Troubleshooting). Simpler to
  just use the 2 GB size for the demo week.

> 💲 **Check current pricing yourself** for your chosen size + region on the AWS
> EC2 pricing page / Pricing Calculator. Do not rely on any remembered figure.
> Note whether your account still has Free Tier credit and what it covers.

**Console steps:**
1. **EC2** → pick a region close to you (top-right region selector). Remember it.
2. **Launch instance**.
3. **Name:** `cloudguard-prod`.
4. **AMI:** **Ubuntu Server 24.04 LTS** (or the latest Ubuntu LTS), 64-bit x86.
5. **Instance type:** the 2 GB-RAM general-purpose size discussed above
   (e.g. `t3.small`). Verify its price first.
6. **Key pair:** **Create new key pair** → name `cloudguard-key` → **.pem**
   format → **Download**. Save it somewhere safe; you cannot re-download it.
   - On WSL, move it into Linux and lock permissions:
     ```bash
     mkdir -p ~/.ssh
     mv /mnt/c/Users/<you>/Downloads/cloudguard-key.pem ~/.ssh/
     chmod 400 ~/.ssh/cloudguard-key.pem
     ```
7. **Network settings** → **Edit**. We define the firewall here (Step 2).
8. **Storage:** the default ~8 GB is tight once images are built. Bump the root
   volume to **16 GB gp3**.
9. **Launch instance.**

After it boots, note the **Public IPv4 address** from the instance details. (It
changes on stop/start unless you attach an Elastic IP — for a short-lived demo,
just avoid stopping it, or allocate an EIP and remember to release it later.)

---

## Step 2 — Security group (firewall) rules

Goal: the web open to everyone, SSH open only to you.

In the launch wizard's **Network settings** (or later under **Security Groups**),
create/edit the instance's security group with exactly these **inbound** rules:

| Type        | Protocol | Port | Source        | Why                              |
|-------------|----------|------|---------------|----------------------------------|
| HTTP        | TCP      | 80   | `0.0.0.0/0`   | Caddy ACME challenge + redirect  |
| HTTPS       | TCP      | 443  | `0.0.0.0/0`   | The actual app over TLS          |
| SSH         | TCP      | 22   | **My IP**     | Admin access — you only          |

- For the SSH rule, choose **Source → My IP** in the console; it fills in your
  current public IP as `x.x.x.x/32`. **Never leave 22 open to `0.0.0.0/0`.**
- Leave **outbound** at the default (allow all) — the box needs it to pull
  Docker images and reach AWS APIs.

> 📶 Your home IP can change. If SSH suddenly times out later, re-edit this rule
> and set **My IP** again. (Find your current IP with `curl ifconfig.me`.)
> Port 80 must stay open to the world or Caddy cannot get/renew its certificate.

---

## Step 3 — Install Docker + the Compose plugin

SSH in from WSL:
```bash
ssh -i ~/.ssh/cloudguard-key.pem ubuntu@<PUBLIC_IP>
```
(Type `yes` at the host-authenticity prompt the first time.)

Then install Docker from Docker's official apt repository (gets the modern
`docker compose` plugin, not the old `docker-compose` script):
```bash
# Refresh + prerequisites
sudo apt-get update
sudo apt-get install -y ca-certificates curl

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install engine + CLI + compose plugin
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# Run docker without sudo
sudo usermod -aG docker ubuntu
```
**Log out and back in** (`exit`, then `ssh` again) so the group change applies.

Verify:
```bash
docker --version
docker compose version
docker run --rm hello-world
```

---

## Step 4 — Point a hostname at the instance (required for HTTPS)

**Let's Encrypt cannot issue a certificate for a bare IP address.** You need a
hostname that resolves to your EC2 public IP. Pick ONE option:

- **A cheap real domain** (Namecheap, Porkbun, Cloudflare Registrar, etc.) —
  most professional for a viva. Create an **A record** pointing the domain (or a
  subdomain) at your EC2 public IP.
- **A free dynamic-DNS / wildcard-DNS service**, e.g. **DuckDNS**
  (`yourname.duckdns.org`), or **nip.io** / **sslip.io** (which encode the IP in
  the hostname, like `1-2-3-4.nip.io`).

> ⚠️ **Verify the free options yourself before relying on one.** These services
> come and go, and their Let's Encrypt compatibility / rate-limit behavior can
> change. Confirm the one you pick is currently up and issuing, *before* your
> defense — don't discover it's down on demo day.

**Using DuckDNS (free, named hostname):**
1. Go to duckdns.org, sign in, create a subdomain (e.g. `cloudguard`).
2. Set its **current ip** field to your EC2 public IPv4 → **update ip**.
3. Your hostname is `cloudguard.duckdns.org`.

**Verify resolution from WSL** before continuing:
```bash
dig +short cloudguard.duckdns.org      # should print your EC2 public IP
```
If it doesn't resolve yet, wait a minute and retry — DNS can lag.

---

## Step 5 — Clone the repo, set `.env.prod`, bring up the stack

On the EC2 box:
```bash
git clone <YOUR_REPO_URL> cloudguard
cd cloudguard
git checkout phase-6-deployment-setup     # or whichever branch is current
```
> If the repo is private, use an HTTPS URL with a GitHub personal-access token,
> or add a deploy key. Don't copy your real `.env.prod` into git — write it on
> the box (next).

**Create `.env.prod` from the template and fill in REAL values:**
```bash
cp .env.prod.example .env.prod
nano .env.prod
```
Set, at minimum:
- `POSTGRES_PASSWORD` — a strong password, **and** mirror it inside
  `DATABASE_URL` (the password appears in both places).
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — a **read-only** IAM key for the
  scheduler/system account.
- `SECRET_KEY`, `ACCESS_TOKEN_SECRET` — **freshly generated** long random
  strings (do NOT reuse your laptop's dev values on a public box):
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- `ENCRYPTION_KEY` — a **fresh** Fernet key:
  ```bash
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  (If `cryptography` isn't installed on the host, generate it once inside the
  built backend image: `docker compose -f docker-compose.prod.yml run --rm
  backend python -c "from cryptography.fernet import Fernet;
  print(Fernet.generate_key().decode())"` — but the host one-liner is simpler if
  Python + cryptography are available.)
- **`DOMAIN`** — your hostname from Step 4, e.g. `cloudguard.duckdns.org`
  (this is what flips Caddy from local HTTP into HTTPS mode).
- **`ADMIN_EMAIL`** — your email, for Let's Encrypt expiry notices.
- `DEBUG=False`, `ENVIRONMENT=production`, `ENABLE_SCHEDULER=true`.

**Build and start the whole stack (detached):**
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
First run takes a few minutes (it builds both images). Check everything is up:
```bash
docker compose -f docker-compose.prod.yml ps
```
All services should be `running`/`healthy` (Postgres has a healthcheck the
backend waits on).

**Run database migrations** (creates all tables) inside the backend container:
```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```
You should see Alembic apply each revision up to `head`.

---

## Step 6 — Confirm Caddy obtained HTTPS automatically

Watch Caddy negotiate the certificate:
```bash
docker compose -f docker-compose.prod.yml logs -f caddy
```
Look for lines like `certificate obtained successfully` for your domain, then
`Ctrl-C` to stop following.

**Test it:**
```bash
curl -I https://cloudguard.duckdns.org/        # expect HTTP/2 200
curl -s https://cloudguard.duckdns.org/api/v1/health   # expect {"status":...}
```
Then open **https://your-domain** in a browser:
- ✅ Padlock shown (valid cert, no warning).
- ✅ The CloudGuard login page loads.
- ✅ Register an account, log in.
- ✅ Settings page loads; you can save read-only AWS credentials.
- ✅ Costs / Alerts / Recommendations pages work.
- ✅ Refreshing on a deep link (e.g. `/settings`) still loads (SPA fallback).

**If the cert didn't issue**, see Troubleshooting below — 99% of the time it's
port 80 not open to the world, DNS not yet pointing at the box, or `DOMAIN`
still set to `localhost`.

---

## Updating the deployment later

After pushing code changes:
```bash
cd ~/cloudguard
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head   # if migrations changed
```

---

## 🔻 Teardown (do this after your defense to stop charges)

Charges keep accruing until the instance is **terminated** and its storage is
deleted. "Stopped" is not "free" — a stopped instance still bills for its EBS
volume.

**On the box (optional, quick):**
```bash
docker compose -f docker-compose.prod.yml down -v   # stop stack + delete its volumes
```

**In the AWS Console (the part that actually stops billing):**
1. **EC2 → Instances** → select `cloudguard-prod` → **Instance state → Terminate
   instance**. Confirm. (Terminate, not just Stop.)
2. **EC2 → Elastic Block Store → Volumes** → if any volume from this instance is
   left as **available** (didn't auto-delete), select it → **Delete volume**.
3. **EC2 → Elastic IPs** → if you allocated one, **Release** it (an unassociated
   Elastic IP bills on its own).
4. **EC2 → Security Groups / Key Pairs** → optionally delete the ones you made.
5. **CloudWatch → Alarms** → you can leave the billing alarm in place (it's
   free) as ongoing insurance, or delete it + its SNS topic if you're done.
6. **Billing → Bills** the next day → confirm charges have stopped.

> ✅ Keep the billing alarm from Step 0 until you've confirmed `$0`/day. It's
> your proof that teardown worked.

---

## Troubleshooting

- **`npm run build` killed / backend build OOMs:** the instance has too little
  RAM. Either use the larger (2 GB) size, or add swap before building:
  ```bash
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  ```
- **Caddy can't get a cert:** confirm `dig +short <domain>` returns the EC2 IP;
  confirm SG port **80** is open to `0.0.0.0/0`; confirm `DOMAIN` in `.env.prod`
  is the real hostname (not `localhost`); then
  `docker compose -f docker-compose.prod.yml restart caddy` and re-check logs.
  Let's Encrypt has rate limits — avoid repeatedly recreating; fix the root
  cause first.
- **SSH times out:** your home IP changed. Re-set the SG rule for port 22 to
  **My IP** (`curl ifconfig.me` shows your current one).
- **Backend unhealthy / DB connection refused:** check
  `docker compose -f docker-compose.prod.yml logs backend` and confirm the
  `POSTGRES_PASSWORD` matches the password embedded in `DATABASE_URL`.
- **Site loads on http:// but not https://:** `DOMAIN` is probably still
  `localhost`; set it to your hostname and `up -d` again.
