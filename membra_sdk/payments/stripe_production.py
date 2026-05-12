"""Stripe Production Integration — Real payment processing with test-key enforcement.

⚠️ REQUIREMENTS FOR PRODUCTION:
- Stripe account with Connect enabled
- STRIPE_SECRET_KEY must start with 'sk_test_' or 'sk_live_'
- STRIPE_PUBLISHABLE_KEY must start with 'pk_test_' or 'pk_live_'
- Webhook endpoint configured for: payment_intent.succeeded, charge.succeeded
- PCI compliance review if storing any card data (MEMBRA does NOT store cards)

This module ONLY works in PRODUCTION mode. SIMULATION mode uses mock receipts.
"""
import os
import time
from typing import Dict, Optional


class StripeProductionError(Exception):
    """Raised when Stripe production requirements are not met."""
    pass


class StripeProductionClient:
    """Production Stripe client for real payment processing.

    DISABLED in SIMULATION mode. Must set MEMBRA_MODE=production to enable.
    """

    def __init__(self):
        self.mode = os.environ.get("MEMBRA_MODE", "simulation").lower()
        self.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        self._validate_environment()

    def _validate_environment(self):
        """Validate that production environment is properly configured."""
        if self.mode != "production":
            raise StripeProductionError(
                f"Stripe production client disabled in '{self.mode}' mode. "
                "Set MEMBRA_MODE=production to enable real payments."
            )

        if not self.api_key:
            raise StripeProductionError(
                "STRIPE_SECRET_KEY not set. Add to environment or macOS Keychain."
            )

        if self.api_key.startswith("sk_test_"):
            # Test mode is allowed for development
            pass
        elif self.api_key.startswith("sk_live_"):
            # Live mode requires additional checks
            if os.environ.get("STRIPE_LIVE_ACKNOWLEDGED") != "I_UNDERSTAND_REAL_MONEY":
                raise StripeProductionError(
                    "Live Stripe key detected. Set STRIPE_LIVE_ACKNOWLEDGED=I_UNDERSTAND_REAL_MONEY "
                    "to confirm you understand this will process real money."
                )
        else:
            raise StripeProductionError(
                "STRIPE_SECRET_KEY must start with 'sk_test_' or 'sk_live_'. "
                "Never commit keys to source control."
            )

    def create_payment_intent(self, amount_usd: float, buyer_email: str,
                              metadata: Dict) -> Dict:
        """Create a Stripe PaymentIntent for a build bounty.

        Returns payment intent ID and client secret for frontend.
        """
        if self.mode != "production":
            return {"error": "Stripe disabled in simulation mode"}

        try:
            import stripe
            stripe.api_key = self.api_key

            intent = stripe.PaymentIntent.create(
                amount=int(amount_usd * 100),  # cents
                currency="usd",
                receipt_email=buyer_email,
                metadata={
                    "membra_job_id": metadata.get("job_id", ""),
                    "membra_buyer_id": metadata.get("buyer_id", ""),
                    "membra_builder_id": metadata.get("builder_id", ""),
                    "source": "membra_marketplace",
                },
            )
            return {
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
                "status": intent.status,
                "amount": amount_usd,
            }
        except Exception as e:
            return {"error": str(e)}

    def verify_payment(self, payment_intent_id: str) -> Dict:
        """Verify a PaymentIntent succeeded and retrieve receipt details."""
        if self.mode != "production":
            return {"verified": False, "error": "Stripe disabled in simulation mode"}

        try:
            import stripe
            stripe.api_key = self.api_key

            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            if intent.status != "succeeded":
                return {
                    "verified": False,
                    "status": intent.status,
                    "error": f"Payment status: {intent.status}",
                }

            # Get charge details
            charges = intent.charges.data
            if not charges:
                return {"verified": False, "error": "No charges found"}

            charge = charges[0]
            return {
                "verified": True,
                "payment_intent_id": intent.id,
                "charge_id": charge.id,
                "amount_usd": intent.amount / 100,
                "currency": intent.currency,
                "receipt_url": charge.receipt_url,
                "receipt_number": charge.receipt_number,
                "status": intent.status,
                "created": intent.created,
            }
        except Exception as e:
            return {"verified": False, "error": str(e)}

    def create_payout(self, builder_account_id: str, amount_usd: float,
                     job_id: str) -> Dict:
        """Create a Stripe Connect payout to a builder's connected account."""
        if self.mode != "production":
            return {"error": "Stripe disabled in simulation mode"}

        try:
            import stripe
            stripe.api_key = self.api_key

            transfer = stripe.Transfer.create(
                amount=int(amount_usd * 100),
                currency="usd",
                destination=builder_account_id,
                metadata={
                    "membra_job_id": job_id,
                    "type": "builder_payout",
                },
            )
            return {
                "transfer_id": transfer.id,
                "amount_usd": amount_usd,
                "status": transfer.status,
                "destination": builder_account_id,
            }
        except Exception as e:
            return {"error": str(e)}

    def handle_webhook(self, payload: bytes, signature: str,
                      secret: str) -> Dict:
        """Handle Stripe webhook event."""
        if self.mode != "production":
            return {"handled": False, "error": "Stripe disabled in simulation mode"}

        try:
            import stripe
            event = stripe.Webhook.construct_event(payload, signature, secret)

            if event.type == "payment_intent.succeeded":
                return {
                    "handled": True,
                    "event": event.type,
                    "payment_intent_id": event.data.object.id,
                    "amount": event.data.object.amount / 100,
                }
            elif event.type == "charge.succeeded":
                return {
                    "handled": True,
                    "event": event.type,
                    "charge_id": event.data.object.id,
                }
            else:
                return {"handled": True, "event": event.type, "note": "no action"}
        except Exception as e:
            return {"handled": False, "error": str(e)}
