# Security setup - do these in order

## 1. Set secrets in Vercel BEFORE deploying
Vercel > your project > Settings > Environment Variables (see `.env.example`):

| Name | Value |
|---|---|
| `JWT_SECRET_KEY` | random, 32+ chars: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | your PostgreSQL connection string |

The site **refuses to start** on Vercel without a strong `JWT_SECRET_KEY`. That is intentional:
the old fallback value (`abcdefg`) let anyone forge an admin login token.

## 2. Deploy, then replace the old admin password
The old code created the admin with password `admin123`. On the live site, logging in with that
password is now refused. Set a real one (hidden prompt, 12+ characters):

    DATABASE_URL="<same value as on Vercel>" python admin.py

## 3. Turn on Row Level Security
Open your database's SQL editor and run `security.sql` (safe to run again). It denies every
database role except your Flask connection, so a leaked URL or public key cannot read or edit rows.

## 4. Vercel dashboard (this stops floods before they reach your code and your bill)
* Settings > Spend Management: set a spend limit / alerts.
* Firewall: add a rate-limit rule on `/api/*`, and know where Attack Challenge Mode is for emergencies.

## What the code now does
* No secrets in front-end code; none have defaults. Everything sensitive is a server env variable.
* Rate limits per visitor IP, stored in the database (works across Vercel's many instances):
  login 5/min + 30/hour, orders 10 per 10 min, bookings 5 per 10 min, lookups 15/min, whole API 300/min.
* Login: per-username lockout after 8 failures in 15 min (stops attacks spread over many IPs),
  same response time for unknown users, no default password, tokens die when an admin is deleted.
* Stored-XSS fixed: visitor-written names were rendered unescaped in the admin pages, which could
  steal the admin token. All templates now escape (`safe.js`), and a strict Content-Security-Policy blocks injected scripts.
* Input limits: body size, name lengths, item counts, quantities, totals, stay length, NaN/Infinity, image paths.
* Security headers, no stack traces to visitors, no debug mode, small DB connection pool.

## Known limits (honest list)
* Visitors behind one shared IP (hotel wifi) share a rate-limit budget. Numbers are in `app.py` (`@rate_limit(...)`).
* Fake bookings count as "pending" and hold rooms. Rate limits slow this down but only a CAPTCHA
  (e.g. Cloudflare Turnstile) or a confirmation step fully stops it.
* The admin token is kept in browser storage for 1 hour. Moving it to an HttpOnly cookie is the next upgrade.
* Orders/bookings are looked up by ID + name. Rate limited, but a random lookup code would be stronger.
* Someone can deliberately trigger the 15-minute lockout on the `admin` username (they cannot get in, only delay you).
