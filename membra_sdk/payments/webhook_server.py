"""Stripe Webhook Server — Listens for checkout.session.completed events.

Runs on localhost:4242 by default. Use Stripe CLI to forward webhooks:
    stripe listen --forward-to localhost:4242/webhook

Or expose with ngrok:
    ngrok http 4242
    stripe listen --forward-to https://your-ngrok-url/webhook
"""
import hashlib
import json
import os
import sys
import time
from threading import Thread

from flask import Flask, request, jsonify

sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.payments.stripe_checkout import MembraStripeCheckout
from membra_sdk.builder.artifact_builder import ArtifactBuilder
from membra_sdk.core.ledger import InternalLedger

app = Flask(__name__)

# Shared state
ledger = InternalLedger()
builder = ArtifactBuilder()
confirmed_payments = {}


@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events."""
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        checkout = MembraStripeCheckout()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400

    # Verify webhook
    event = checkout.verify_webhook(payload, sig_header)
    if not event:
        return jsonify({"error": "Invalid webhook signature"}), 400

    event_type = event.get("type", "")
    event_data = event.get("data", {})

    print(f"[WEBHOOK] Received: {event_type}")

    if event_type == "checkout.session.completed":
        result = checkout.handle_checkout_completed(event_data)

        if result.get("verified"):
            session_id = result["session_id"]
            job_id = result["job_id"]
            amount = result["amount_usd"]

            print(f"[PAYMENT] Verified: ${amount:.2f} for job {job_id}")
            confirmed_payments[session_id] = result

            # ONLY NOW: Build the artifact (after payment confirmed)
            print(f"[BUILD] Starting artifact build for {job_id}...")
            build_result = builder.build(
                job_id=job_id,
                spec={
                    "type": "python_script",
                    "description": "AI-generated utility function",
                    "function_name": "membra_task",
                    "job_id": job_id,
                }
            )

            if build_result["status"] == "built":
                print(f"[BUILD] Success: {build_result['filename']}")
                print(f"[BUILD] Hash: {build_result['content_hash'][:16]}...")

                # Generate ZIP report
                zip_path = builder.generate_report_zip(build_result, result)
                print(f"[REPORT] Generated: {zip_path}")

                # Split revenue in ledger
                splits = split_revenue(session_id, amount, build_result)
                print(f"[LEDGER] Revenue split recorded:")
                for k, v in splits.items():
                    print(f"  {k}: ${v:.2f}")

                return jsonify({
                    "status": "success",
                    "job_id": job_id,
                    "amount": amount,
                    "artifact": build_result["filename"],
                    "hash": build_result["content_hash"],
                    "report_zip": zip_path,
                    "splits": splits,
                }), 200
            else:
                print(f"[BUILD] Failed: {build_result['test_result']}")
                return jsonify({
                    "status": "build_failed",
                    "job_id": job_id,
                    "error": build_result["test_result"],
                }), 200

        else:
            return jsonify({
                "status": "payment_not_verified",
                "reason": result.get("reason", ""),
            }), 200

    return jsonify({"status": "ignored", "event": event_type}), 200


@app.route("/success")
def success():
    """Show success page after checkout."""
    session_id = request.args.get("session_id", "")
    job_id = request.args.get("job_id", "")
    return f"""
    <h1>Payment Successful</h1>
    <p>Session: {session_id}</p>
    <p>Job ID: {job_id}</p>
    <p>Your artifact is being built. Check the webhook server logs.</p>
    <p>ZIP report will be available at: ~/.membra/builds/{job_id}_report.zip</p>
    """


@app.route("/cancel")
def cancel():
    job_id = request.args.get("job_id", "")
    return f"""
    <h1>Payment Cancelled</h1>
    <p>Job ID: {job_id}</p>
    <p>No payment was processed. You can try again.</p>
    """


@app.route("/status/<session_id>")
def status(session_id: str):
    """Check status of a payment session."""
    payment = confirmed_payments.get(session_id)
    if not payment:
        return jsonify({"status": "pending", "session_id": session_id})
    return jsonify(payment)


def split_revenue(session_id: str, amount: float, build_result: dict) -> dict:
    """Split confirmed revenue according to policy."""
    # Distribution policy
    infrastructure = amount * 0.15
    validator = amount * 0.20
    builder_reward = amount * 0.45
    treasury = amount * 0.10
    risk = amount * 0.10

    # Log to internal ledger
    ledger.submit({
        "type": "revenue_split",
        "session_id": session_id,
        "amount": amount,
        "infrastructure": infrastructure,
        "validator": validator,
        "builder": builder_reward,
        "treasury": treasury,
        "risk": risk,
        "artifact_hash": build_result.get("content_hash", ""),
        "timestamp": time.time(),
    })

    return {
        "total": amount,
        "infrastructure": round(infrastructure, 2),
        "validator": round(validator, 2),
        "builder": round(builder_reward, 2),
        "treasury": round(treasury, 2),
        "risk": round(risk, 2),
    }


def run_server(port: int = 4242):
    """Run the webhook server."""
    print(f"[SERVER] Starting webhook server on port {port}")
    print(f"[SERVER] Stripe webhook endpoint: http://localhost:{port}/webhook")
    print(f"[SERVER] Status check: http://localhost:{port}/status/<session_id>")
    print("[SERVER] Use: stripe listen --forward-to localhost:{port}/webhook")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run_server()
