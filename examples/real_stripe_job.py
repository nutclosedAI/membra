#!/usr/bin/env python3
"""
REAL Stripe Job — End-to-end paid artifact build.

This script:
  1. Creates a real Stripe Checkout Session for $25
  2. Prints the checkout URL for the buyer
  3. Starts a webhook server to receive payment confirmation
  4. When Stripe confirms payment, builds the artifact
  5. Generates a downloadable ZIP report
  6. Splits revenue in the internal ledger

REQUIREMENTS:
  1. Stripe account (free): https://dashboard.stripe.com/register
  2. Test API keys from: https://dashboard.stripe.com/test/apikeys
  3. Environment variables set (see below)
  4. stripe CLI installed: https://stripe.com/docs/stripe-cli

SETUP:
  export MEMBRA_MODE=production
  export STRIPE_SECRET_KEY=sk_test_...
  export STRIPE_WEBHOOK_SECRET=whsec_...  # from: stripe listen --print-secret

RUN:
  Terminal 1: python3 examples/real_stripe_job.py
  Terminal 2: stripe listen --forward-to localhost:4242/webhook
  Then: Open the checkout URL in browser, pay with test card:
        Card: 4242 4242 4242 4242
        Expiry: Any future date
        CVC: Any 3 digits
"""
import json
import os
import sys
import time
from threading import Thread

sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.payments.stripe_checkout import MembraStripeCheckout
from membra_sdk.payments.webhook_server import run_server


def main():
    print("=" * 70)
    print("  MEMBRA REAL STRIPE JOB — $25 AI Artifact Build")
    print("=" * 70)
    print()

    # Verify environment
    mode = os.environ.get("MEMBRA_MODE", "simulation")
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")

    if mode != "production":
        print("❌ ERROR: MEMBRA_MODE must be set to 'production'")
        print("   export MEMBRA_MODE=production")
        return 1

    if not stripe_key:
        print("❌ ERROR: STRIPE_SECRET_KEY not set")
        print("   Get your test key from: https://dashboard.stripe.com/test/apikeys")
        print("   export STRIPE_SECRET_KEY=sk_test_...")
        return 1

    if not stripe_key.startswith(("sk_test_", "sk_live_")):
        print("❌ ERROR: STRIPE_SECRET_KEY must start with sk_test_ or sk_live_")
        return 1

    print("✅ Environment configured:")
    print(f"   Mode: {mode}")
    print(f"   Stripe key: {stripe_key[:12]}...")
    print()

    # Create checkout session
    print("[1/4] Creating Stripe Checkout Session...")
    try:
        checkout = MembraStripeCheckout()
        session = checkout.create_checkout_session(
            buyer_email="buyer@example.com",
        )
    except Exception as e:
        print(f"❌ Failed to create checkout session: {e}")
        return 1

    print(f"   Job ID: {session['job_id']}")
    print(f"   Session ID: {session['session_id']}")
    print(f"   Amount: ${session['amount_usd']:.2f}")
    print()
    print("=" * 70)
    print("  CHECKOUT URL (send this to buyer):")
    print(f"  {session['checkout_url']}")
    print("=" * 70)
    print()

    # Start webhook server in background
    print("[2/4] Starting webhook server...")
    print("   In another terminal, run:")
    print("   stripe listen --forward-to localhost:4242/webhook")
    print()

    # Save session info for webhook handler
    info_path = os.path.expanduser("~/.membra/last_session.json")
    os.makedirs(os.path.dirname(info_path), exist_ok=True)
    with open(info_path, "w") as f:
        json.dump(session, f, indent=2)

    print("[3/4] Waiting for payment confirmation via webhook...")
    print("   Server running on http://localhost:4242")
    print("   Status check: http://localhost:4242/status/" + session["session_id"])
    print()
    print("   When buyer pays, the webhook will:")
    print("     1. Verify the Stripe payment")
    print("     2. Build the artifact")
    print("     3. Generate ZIP report")
    print("     4. Split revenue in ledger")
    print()

    # Run server (blocks)
    try:
        run_server(port=4242)
    except KeyboardInterrupt:
        print("\n[4/4] Server stopped.")
        print("   Check ~/.membra/builds/ for generated artifacts and reports.")
        print("   Check ~/.membra/stripe_payments.json for confirmed payments.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
