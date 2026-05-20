-- seed_demo_data.sql
-- Inserts 30 days of realistic-looking AWS cost data for demo/screenshots.
-- Run this when your AWS account has no real billing data.
--
-- Usage (from pgAdmin Query Tool, or psql):
--   \i /path/to/seed_demo_data.sql
--
-- To undo:
--   TRUNCATE cost_records CASCADE;
--   DELETE FROM aws_accounts WHERE account_id = '123456789012';

-- ── 1. Create a demo AWS account row ────────────────────────────────────────
INSERT INTO aws_accounts (account_id, alias, created_at)
VALUES ('123456789012', 'demo-account', NOW())
ON CONFLICT (account_id) DO NOTHING;

-- ── 2. Insert 30 days × 6 services of cost data ─────────────────────────────
-- Services and their approximate daily costs (USD) — realistic free-tier-adjacent numbers
-- EC2 ~$1.20/day, S3 ~$0.15/day, RDS ~$0.80/day, Lambda ~$0.05/day,
-- CloudFront ~$0.10/day, Data Transfer ~$0.25/day

WITH
  acct AS (SELECT id FROM aws_accounts WHERE account_id = '123456789012'),
  days AS (
    SELECT generate_series(
      CURRENT_DATE - INTERVAL '29 days',
      CURRENT_DATE,
      INTERVAL '1 day'
    )::date AS d
  ),
  services(name, base, variance) AS (
    VALUES
      ('Amazon EC2',                1.2000, 0.3000),
      ('Amazon S3',                 0.1500, 0.0500),
      ('Amazon RDS',                0.8000, 0.2000),
      ('AWS Lambda',                0.0500, 0.0200),
      ('Amazon CloudFront',         0.1000, 0.0400),
      ('AWS Data Transfer',         0.2500, 0.0800)
  )
INSERT INTO cost_records (aws_account_id, date, service_name, amount_usd, created_at)
SELECT
  acct.id,
  days.d,
  services.name,
  -- base cost + small random variation, rounded to 4dp
  ROUND(
    (services.base + services.variance * (random() - 0.5) * 2)::numeric,
    4
  ),
  NOW()
FROM days
CROSS JOIN services
CROSS JOIN acct
ON CONFLICT (aws_account_id, date, service_name) DO UPDATE
  SET amount_usd = EXCLUDED.amount_usd;

-- ── 3. Quick check ────────────────────────────────────────────────────────────
SELECT
  service_name,
  COUNT(*)       AS days,
  ROUND(SUM(amount_usd), 2) AS total_usd
FROM cost_records cr
JOIN aws_accounts aa ON aa.id = cr.aws_account_id
WHERE aa.account_id = '123456789012'
GROUP BY service_name
ORDER BY total_usd DESC;
