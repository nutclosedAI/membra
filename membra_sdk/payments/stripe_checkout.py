"""Stripe Checkout — Real payment integration for MEMBRA marketplace jobs.

This module creates real Stripe Checkout Sessions for buyers to pay for
AI artifact builds. It requires a real Stripe account and API key.

Environment:
    STRIPE_SECRET_KEY=sk_test_...     # Required
    STRIPE_WEBHOOK_SECRET=whsec_...   # Optional but recommended for webhook verification
    MEMBRA_MODE=production            # Required to enable real payments

Usage:
    python3 examples/real_stripe_job.py
"""
import hashlib
import json
import os
import time
from typing import Dict, Optional

import stripe

from membra_sdk.config import MembraConfig


class StripeCheckoutError(Exception):
    """Raised when Stripe checkout fails."""
    pass


class MembraStripeCheckout:
    """Real Stripe Checkout integration for MEMBRA build jobs.

    Creates a Checkout Session for a $25 AI artifact build.
    Buyer pays via Stripe. Webhook confirms settlement.
    Only then does MEMBRA mark revenue as verified.
    """

    PRODUCT_NAME = "AI Artifact Build"
    PRODUCT_DESCRIPTION = "Custom AI-generated code artifact with tests, hash, and build report"
    AMOUNT_USD = 25.00

    def __init__(self):
        self.config = MembraConfig()
        if self.config.is_simulation():
            raise RuntimeError(
                "Stripe checkout requires MEMBRA_MODE=production. "
                "Set the environment variable and provide a real Stripe key."
            )

        self.api_key = self.config.stripe_secret_key
        if not self.api_key:
            raise RuntimeError(
                "STRIPE_SECRET_KEY not set. Get your test key from https://dashboard.stripe.com/test/apikeys"
            )

        stripe.api_key = self.api_key
        self.webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

        # Storage for confirmed payments
        self.confirmed_payments: Dict[str, Dict] = {}
        self.storage_path = os.path.expanduser("~/.membra/stripe_payments.json")
        self._load_payments()

    def create_checkout_session(self, buyer_email: str, job_id: str = None) -> Dict:
        """Create a Stripe Checkout Session for a $25 AI artifact build.

        Returns:
            {
                "session_id": str,
                "checkout_url": str,
                "job_id": str,
                "amount_usd": 25.00,
                "status": "created",
            }
        """
        job_id = job_id or f"job-{int(time.time())}-{hashlib.sha256(buyer_email.encode()).hexdigest()[:8]}"

        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": self.PRODUCT_NAME,
                            "description": self.PRODUCT_DESCRIPTION,
                        },
                        "unit_amount": int(self.AMOUNT_USD * 100),  # $25.00 in cents
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=f"http://localhost:8080/success?session_id={{CHECKOUT_SESSION_ID}}&job_id={job_id}",
                cancel_url=f"http://localhost:8080/cancel?job_id={job_id}",
                customer_email=buyer_email,
                metadata={
                    "membra_job_id": job_id,
                    "membra_product": "ai_artifact_build",
                    "membra_amount_usd": str(self.AMOUNT_USD),
                },
            )

            result = {
                "session_id": session.id,
                "checkout_url": session.url,
                "job_id": job_id,
                "amount_usd": self.AMOUNT_USD,
                "buyer_email": buyer_email,
                "status": "created",
                "created_at": time.time(),
            }
            self._save_payment(result)
            return result

        except stripe.error.StripeError as e:
            raise StripeCheckoutError(f"Stripe API error: {e}")

    def verify_webhook(self, payload: bytes, signature: str) -> Optional[Dict]:
        """Verify and parse a Stripe webhook event.

        Returns the event dict if valid, None if invalid.
        """
        if not self.webhook_secret:
            # Without webhook secret, parse raw JSON (less secure)
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return None

        try:
            event = stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
            return {
                "id": event.id,
                "type": event.type,
                "data": event.data.object,
            }
        except stripe.error.SignatureVerificationError:
            return None
        except Exception:
            return None

    def handle_checkout_completed(self, session: Dict) -> Dict:
        """Process checkout.session.completed webhook.

        This is the ONLY place where MEMBRA marks revenue as verified.
        """
        session_id = session.get("id", "")
        job_id = session.get("metadata", {}).get("membra_job_id", "")
        amount_received = session.get("amount_total", 0) / 100  # cents to USD
        payment_status = session.get("payment_status", "")
        customer_email = session.get("customer_email", "")
        customer_id = session.get("customer", "")

        if payment_status != "paid":
            return {
                "verified": False,
                "reason": f"Payment status is '{payment_status}', not 'paid'",
                "session_id": session_id,
            }

        # Payment is real and confirmed by Stripe
        confirmed = {
            "session_id": session_id,
            "job_id": job_id,
            "amount_usd": amount_received,
            "currency": session.get("currency", "usd"),
            "payment_status": payment_status,
            "customer_email": customer_email,
            "customer_id": customer_id,
            "payment_intent": session.get("payment_intent", ""),
            "receipt_url": session.get("url", ""),  # May need charge.receipt_url
            "verified": True,
            "verified_at": time.time(),
            "source": "stripe_webhook",
        }

        self.confirmed_payments[session_id] = confirmed
        self._save_payment(confirmed)

        return confirmed

    def get_confirmed_payment(self, session_id: str) -> Optional[Dict]:
        return self.confirmed_payments.get(session_id)

    def list_confirmed_payments(self) -> list:
        return list(self.confirmed_payments.values())

    def _save_payment(self, payment: Dict):
        """Persist payment record to local JSON."""
        self.confirmed_payments[payment.get("session_id", "")] = payment
        try:
            with open(self.storage_path, "w") as f:
                json.dump(self.confirmed_payments, f, indent=2, default=str)
        except Exception:
            pass

    def _load_payments(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path) as f:
                self.confirmed_payments = json.load(f)
        except Exception:
            self.confirmed_payments = {}
