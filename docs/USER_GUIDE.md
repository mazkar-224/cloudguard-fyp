# CloudGuard — User Guide

This guide walks a brand-new user through everything: creating an account,
connecting an AWS account with read-only keys, and reading each screen.

**Live app:** https://cloudcostguard-fyp.duckdns.org
(or `http://localhost:5173` if you're running it locally).

---

## 1. Create an account

1. Open the app. If you're not signed in you'll land on the **Login** screen.
2. Click **"Create one"** (or go to `/register`).
3. Enter your **email** and a **password**, then submit.
4. CloudGuard creates your account and logs you straight in — you'll arrive at
   the Dashboard. (Behind the scenes you now hold a JWT session token; it keeps
   you signed in across refreshes until you log out or it expires.)

Already have an account? Use **Login** (`/login`) instead.

> **Logging out:** the **Logout** button is at the top-right of every page. It
> clears your session and returns you to the Login screen.

---

## 2. Connect your AWS account (read-only keys)

CloudGuard can't show you anything until it can read your AWS billing data. You
provide an **IAM access key pair** on the Settings page.

### Why read-only?

> ⚠️ **Always use READ-ONLY credentials.** CloudGuard only ever *reads* — it never
> creates, changes, or deletes anything in your account. Create an IAM user with
> the AWS-managed **`ReadOnlyAccess`** policy (or, more narrowly, `ce:GetCostAndUsage`
> plus read-only EC2 and CloudWatch permissions for the waste scanner).

### Steps

1. In AWS, create an IAM user with **ReadOnlyAccess** and generate an **access key**
   (you'll get an *Access key ID* starting with `AKIA…` and a *Secret access key*).
2. In CloudGuard, open **Settings** from the left sidebar.
3. Fill in:
   - **Access key ID** — e.g. `AKIA…`
   - **Secret access key** — the long secret value
   - **Region** — e.g. `us-east-1`
4. *(Optional)* Click **Test connection** to verify the keys reach AWS without
   saving them.
5. Click **Save**. CloudGuard **validates the keys against AWS first** — if they're
   wrong or lack permission, nothing is stored and you'll see an error.

### What happens to your secret

- The access key ID and secret are **encrypted at rest** (Fernet) before they
  touch the database.
- After saving, Settings only ever shows the **last 4 characters** of the access
  key ID plus the region — the **secret is never displayed again**.
- You can **remove** your stored credentials at any time from the same page.

---

## 3. Get your data in

CloudGuard fills the dashboard from two background jobs, which also run on a
schedule:

| Action | Where | What it does |
|--------|-------|--------------|
| **Sync now** | top-right button (most pages) | Pulls the last 7 days of costs from AWS Cost Explorer and runs anomaly detection. |
| **Scan now** | top-right button (Recommendations page) | Runs the waste scan (idle instances, unattached disks, etc.). |

On a schedule, the cost sync runs **every 6 hours** and the resource scan runs
**daily** — so once it's set up, CloudGuard keeps itself up to date. The first
time, click **Sync now** so you don't have to wait.

> If a screen is empty, that usually just means no sync has run yet (or the date
> range genuinely has no spend). Click **Sync now** and refresh.

---

## 4. The Dashboard

The home screen — **"Cost overview"** — is your at-a-glance spending picture.

- **Summary cards** — four headline numbers: spend over the **last 30 days**, the
  **last 7 days**, **yesterday**, and the **week-over-week change %** (so you can
  see if spending is trending up).
- **Daily spend chart** — a line chart of daily total cost. Use the **7 / 30 / 90-day**
  selector to change the window.
- **Service breakdown** — a donut showing your **top 5 services** by cost, with
  everything else grouped as **"Other"**, so you can see what's driving the bill.

Each card and chart shows a loading skeleton while data arrives and a friendly
message if something fails or there's no data yet.

---

## 5. Alerts (anomaly detection)

The **Alerts** screen (🔔 in the sidebar) lists spending **spikes** CloudGuard
detected automatically.

How alerts are created: after each sync, CloudGuard compares each day's spend
(both your **account total** and your **per-service** spend) against a rolling
baseline. A day that's statistically far above normal (a high *z-score*) becomes
an alert, tagged with a **severity** (e.g. medium / high). If email is configured,
you also get a notification.

On the page you can:

- **Filter** by **status** (new / acknowledged) and **severity**, over the last 30 days.
- Read each alert's detail — which service, the date, the amount vs. the baseline,
  and how unusual it was.
- **Acknowledge** an alert once you've looked into it (it moves from *new* to
  *acknowledged*). The sidebar shows a **count badge** of new alerts.

A clean account shows **"No alerts"** — that's the good case.

> Want to see it work in a demo? See `docs/anomaly-detection.md` for how to inject
> a synthetic spike and watch an alert appear.

---

## 6. Recommendations (waste scanner)

The **Recommendations** screen (💡 in the sidebar) is where CloudGuard tells you
what you can safely turn off to save money.

At the top, a **hero banner** shows your **total estimated monthly savings** if you
acted on everything. Below it is a list of findings, each its own card:

- **What it found** — e.g. an **unattached EBS volume**, an **unassociated Elastic IP**,
  a **stopped instance** still paying for storage, an **old snapshot**, or an
  **idle running instance** (low CPU over 14 days).
- **Estimated monthly saving** — an *approximate* dollar figure, used to **rank the
  cards** so the biggest wins are at the top. (Savings are labelled approximate —
  they're based on a documented pricing table, not a live AWS price query.)
- **Why** — a short reason (e.g. "idle for 23 days").

You can:

- **Filter** by **resource type** and **status**.
- **Dismiss** a recommendation you don't care about, or mark it **Resolved** once
  you've cleaned it up.
- Click **Scan now** (top-right) to re-run the scan immediately.

An account with nothing to fix shows **"No waste found — nice!"**

---

## 7. Tips & troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| Everything is empty | No sync has run yet — click **Sync now**. |
| "Save" fails on Settings | The keys are wrong or lack permission — CloudGuard validates before saving. Re-check the key, secret, and region. |
| No alerts ever appear | That's normal for steady spend. Use the demo spike injector (`docs/anomaly-detection.md`) to see one. |
| No recommendations | Either your account is tidy, or the scanner's read-only EC2/CloudWatch permissions are missing. Use **ReadOnlyAccess**. |
| Logged out unexpectedly | Your session token expired — just log back in. |
| Dark mode | Toggle the ☀️/🌙 icon at the top-right; the choice is remembered. |

---

For how the whole system fits together, see **[ARCHITECTURE.md](ARCHITECTURE.md)**.
