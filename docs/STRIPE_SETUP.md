# Stripe Setup Guide — Real Payments for MEMBRA

## Prerequisites

1. **Stripe account** (free): https://dashboard.stripe.com/register
2. **Stripe CLI**: https://stripe.com/docs/stripe-cli
3. **Python packages**: `pip install stripe flask`

## Step-by-Step

### 1. Get Your Test API Keys

1. Log in to https://dashboard.stripe.com/test/dashboard
2. Go to Developers → API keys
3. Copy your **Secret key** (starts with `sk_test_`)
4. Set environment variable:
   ```bash
   export STRIPE_SECRET_KEY=sk_test_...
   export MEMBRA_MODE=production
   ```

### 2. Install Stripe CLI

```bash
# macOS (Homebrew)
brew install stripe/stripe-cli/stripe

# Or download from https://github.com/stripe/stripe-cli/releases
```

### 3. Log In to Stripe CLI

```bash
stripe login
# This opens browser for authentication
```

### 4. Start Webhook Forwarding

```bash
stripe listen --forward-to localhost:4242/webhook
```

This will print a webhook signing secret:
```
> Ready! Your webhook signing secret is whsec_...
```

Set it:
```bash
export STRIPE_WEBHOOK_SECRET=whsec_...
```

### 5. Run the MEMBRA Stripe Job

Terminal 1 (webhook server):
```bash
cd /Users/alep/Downloads/membra-sdk
export MEMBRA_MODE=production
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
python3 examples/real_stripe_job.py
```

Terminal 2 (webhook forwarding):
```bash
stripe listen --forward-to localhost:4242/webhook
```

### 6. Pay with Test Card

When the script prints a checkout URL, open it in browser and use:

| Field | Value |
|-------|-------|
| Card number | `4242 4242 4242 4242` |
| Expiry | Any future date (e.g., 12/30) |
| CVC | Any 3 digits (e.g., 123) |
| ZIP | Any 5 digits (e.g., 12345) |

This is Stripe's test card. No real money is charged.

### 7. Watch the Flow

After payment:
1. Stripe CLI shows the webhook event
2. MEMBRA server receives `checkout.session.completed`
3. Payment is verified
4. Artifact is built
5. ZIP report generated at `~/.membra/builds/<job_id>_report.zip`
6. Revenue split logged to internal ledger

### 8. Verify the Results

```bash
# Check confirmed payments
python3 -c "
import json
with open('~/.membra/stripe_payments.json') as f:
    data = json.load(f)
for sid, payment in data.items():
    print(f'Session: {sid}')
    print(f'  Amount: ${payment[\"amount_usd\"]}')
    print(f'  Verified: {payment[\"verified_at\"]}')
"

# Check generated artifacts
ls ~/.membra/builds/

# Unzip a report
unzip -l ~/.membra/builds/job-xxx_report.zip
```

## Production (Real Money)

To accept real payments:

1. Switch to live keys:
   ```bash
   export STRIPE_SECRET_KEY=sk_live_...
   export STRIPE_LIVE_ACKNOWLEDGED=I_UNDERSTAND_REAL_MONEY
   ```

2. Update success/cancel URLs in `stripe_checkout.py` to your real domain

3. Use Stripe's live dashboard: https://dashboard.stripe.com/live/dashboard

4. Comply with Stripe's requirements (business verification, terms, etc.)

5. **Legal review required** before processing real customer payments

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `No module named 'stripe'` | `pip install stripe` |
| `MEMBRA_MODE must be production` | `export MEMBRA_MODE=production` |
| `STRIPE_SECRET_KEY not set` | `export STRIPE_SECRET_KEY=sk_test_...` |
| Webhook not received | Ensure `stripe listen` is running in another terminal |
| Invalid signature | Ensure `STRIPE_WEBHOOK_SECRET` matches `stripe listen` output |
| Port 4242 in use | Change port in `real_stripe_job.py` and webhook forward URL |

## Architecture

```
Buyer Browser
    |
    | 1. Opens Checkout URL
    v
Stripe Checkout Page
    |
    | 2. Enters test card 4242...
    v
Stripe Servers
    |
    | 3. payment_intent.succeeded
    v
stripe listen (CLI)
    |
    | 4. POST /webhook
    v
MEMBRA Server (localhost:4242)
    |
    | 5. Verifies signature
    | 6. Marks revenue verified
    | 7. Builds artifact
    | 8. Generates ZIP
    | 9. Splits revenue
    v
~/.membra/builds/<job_id>_report.zip
```

## Security Notes

- Never commit `STRIPE_SECRET_KEY` to git
- Never use live keys in development
- Webhook secrets prevent forged events
- Test mode is free and safe for all development

## Next Steps

After first test payment succeeds:
1. Build a web UI for buyers to browse and purchase builds
2. Add builder marketplace (claim jobs, submit artifacts)
3. Add validator network (3+ nodes confirm receipts)
4. Add Solana anchor for proof hashes
5. Switch to live Stripe keys for real customers
