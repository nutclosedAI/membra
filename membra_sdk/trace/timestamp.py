"""RFC 3161 with original DER bytes, explicit trust and offline verification."""

import hashlib
import secrets
import subprocess
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from asn1crypto import tsp

from .crypto import TraceError, fields, hexadecimal, integer, require

MAX_RECEIPT_BYTES = 2_000_000


def make_request(checkpoint_digest: str) -> bytes:
    return tsp.TimeStampReq(
        {
            "version": "v1",
            "message_imprint": {
                "hash_algorithm": {"algorithm": "sha256"},
                "hashed_message": hexadecimal(checkpoint_digest),
            },
            "nonce": secrets.randbits(128) or 1,
            "cert_req": True,
        }
    ).dump()


def request_digest(query: bytes) -> str:
    try:
        obj = tsp.TimeStampReq.load(query, strict=True)
        require(obj["version"].native == "v1", "TSA request version")
        require(
            obj["message_imprint"]["hash_algorithm"]["algorithm"].native == "sha256",
            "TSA request hash",
        )
        require(obj["nonce"].native is not None, "TSA request requires nonce")
        return obj["message_imprint"]["hashed_message"].native.hex()
    except (ValueError, TypeError, KeyError) as exc:
        raise TraceError(f"invalid timestamp request: {exc}") from exc


def submit(query: bytes, provider: str, timeout: int = 30) -> bytes:
    require(provider.startswith("https://"), "TSA provider must use HTTPS")
    request_digest(query)
    req = urllib.request.Request(
        provider,
        data=query,
        headers={
            "Content-Type": "application/timestamp-query",
            "Accept": "application/timestamp-reply",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        require(response.geturl().startswith("https://"), "insecure TSA redirect")
        data = response.read(MAX_RECEIPT_BYTES + 1)
    require(len(data) <= MAX_RECEIPT_BYTES, "timestamp response too large")
    return data


def verify_timestamp(
    receipt: dict, checkpoint_digest: str, ca: Path, trust: dict
) -> dict:
    fields(receipt, "provider request response", "timestamp receipt")
    require(
        isinstance(receipt["provider"], str)
        and receipt["provider"].startswith("https://"),
        "TSA provider",
    )
    ca_data = ca.read_bytes()
    require(
        hashlib.sha256(ca_data).hexdigest() == trust["tsa_ca_sha256"],
        "TSA root pin mismatch",
    )
    integer(trust["tsa_uncertainty_ns"], "TSA uncertainty", 1)
    try:
        require(
            len(receipt["request"]) <= MAX_RECEIPT_BYTES * 2, "TSA request too large"
        )
        require(
            len(receipt["response"]) <= MAX_RECEIPT_BYTES * 2, "TSA response too large"
        )
        query, response = bytes.fromhex(receipt["request"]), bytes.fromhex(
            receipt["response"]
        )
        require(
            request_digest(query) == checkpoint_digest,
            "TSA checkpoint imprint mismatch",
        )
        request = tsp.TimeStampReq.load(query, strict=True)
        reply = tsp.TimeStampResp.load(response, strict=True)
        require(
            reply["status"]["status"].native in ("granted", "granted_with_mods"),
            "TSA rejected request",
        )
        info = reply["time_stamp_token"]["content"]["encap_content_info"][
            "content"
        ].parsed
        signed = reply["time_stamp_token"]["content"]
        require(len(signed["signer_infos"]) == 1, "TSA must have one signer")
        sid = signed["signer_infos"][0]["sid"]
        certificates = [
            c.chosen for c in signed["certificates"] if c.name == "certificate"
        ]
        if sid.name == "issuer_and_serial_number":
            matching = [
                c
                for c in certificates
                if c.serial_number == sid.chosen["serial_number"].native
                and c.issuer.dump() == sid.chosen["issuer"].dump()
            ]
        else:
            matching = [c for c in certificates if c.key_identifier == sid.native]
        require(len(matching) == 1, "TSA signing certificate missing or ambiguous")
        signer_certificate_sha256 = hashlib.sha256(matching[0].dump()).hexdigest()
        require(
            info["message_imprint"].dump() == request["message_imprint"].dump(),
            "TSA response imprint mismatch",
        )
        require(info["nonce"].native == request["nonce"].native, "TSA nonce mismatch")
        generated = info["gen_time"].native
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        delta = generated - epoch
        generated_ns = (
            delta.days * 86400 + delta.seconds
        ) * 1_000_000_000 + delta.microseconds * 1000
        accuracy = info["accuracy"].native or {}
        uncertainty = max(
            trust["tsa_uncertainty_ns"],
            (accuracy.get("seconds") or 0) * 1_000_000_000
            + (accuracy.get("millis") or 0) * 1_000_000
            + (accuracy.get("micros") or 0) * 1000,
        )
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise TraceError(f"invalid timestamp response: {exc}") from exc
    with tempfile.TemporaryDirectory(prefix="trace-verify-") as directory:
        path = Path(directory)
        (path / "request.der").write_bytes(query)
        (path / "response.der").write_bytes(response)
        (path / "ca.pem").write_bytes(ca_data)
        (path / "empty-trust").mkdir()
        # Never fetch certificates or use the platform's ambient trust store.
        try:
            result = subprocess.run(
                [
                    "openssl",
                    "ts",
                    "-verify",
                    "-queryfile",
                    "request.der",
                    "-in",
                    "response.der",
                    "-CAfile",
                    "ca.pem",
                    "-CApath",
                    "empty-trust",
                    "-CAstore",
                    "ca.pem",
                    "-attime",
                    str(generated_ns // 1_000_000_000),
                ],
                capture_output=True,
                cwd=path,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TraceError(
                f"OpenSSL timestamp verification unavailable: {exc}"
            ) from exc
        require(
            result.returncode == 0,
            "TSA signature/certificate verification failed: "
            + result.stderr.decode(errors="replace")[-1500:],
        )
    return {
        "generated_ns": generated_ns,
        "earliest_ns": generated_ns - uncertainty,
        "latest_ns": generated_ns + uncertainty,
        "receipt_digest": hashlib.sha256(response).hexdigest(),
        "signer_certificate_sha256": signer_certificate_sha256,
    }
