"""Offline verification from externally supplied identity, role and TSA trust."""

from pathlib import Path

from .crypto import (
    TraceError,
    commitment,
    digest,
    fields,
    hexadecimal,
    integer,
    require,
    verify_signature,
)
from .timestamp import verify_timestamp

EVENT_FIELDS = (
    "domain chain sequence previous id kind actor key observed_ns appended_ns payload"
)
CHECKPOINT_FIELDS = "domain chain count head actor key created_ns"
KINDS = {
    "observation": "research",
    "forecast": "research",
    "reveal": "research",
    "outcome": "oracle",
    "missing": "oracle",
    "score": "evaluator",
    "decision": "evaluator",
    "authorization": "governor",
    "authorized_action": "executor",
    "epoch": "governor",
    "revoke": "governor",
    "key_rotate": None,
    "key_revoke": "governor",
}


def rotation_message(body: dict, new_key: str) -> dict:
    return {
        "domain": "TRACE-key-rotation-v1",
        "chain": body["chain"],
        "actor": body["actor"],
        "sequence": body["sequence"],
        "previous": body["previous"],
        "new_key": new_key,
    }


def verify_bundle(
    bundle: dict,
    trust: dict,
    *,
    expected_checkpoint: str | None,
    ca: Path | None = None,
    draft: bool = False,
) -> dict:
    """Draft mode is for transactional append validation, never CLI certification."""
    fields(bundle, "format chain events checkpoints anchors", "bundle")
    require(bundle["format"] == "TRACE-bundle-v1", "bundle version")
    fields(
        trust,
        "format chain actors policy epoch risk_limits max_evidence_age_ns tsa_ca_sha256 tsa_uncertainty_ns",
        "trust",
    )
    require(
        trust["format"] == "TRACE-trust-v1" and bundle["chain"] == trust["chain"],
        "trust/chain mismatch",
    )
    hexadecimal(trust["policy"])
    hexadecimal(trust["risk_limits"])
    integer(trust["epoch"], "trust epoch")
    integer(trust["max_evidence_age_ns"], "maximum evidence age", 1)
    require(
        isinstance(bundle["events"], list) and len(bundle["events"]) <= 100_000,
        "event count",
    )
    require(
        isinstance(bundle["checkpoints"], list)
        and len(bundle["checkpoints"]) <= 10_000,
        "checkpoint count",
    )
    require(isinstance(bundle["anchors"], dict), "anchors format")
    actors = trust["actors"]
    require(isinstance(actors, dict) and actors, "no trusted actors")
    keys: dict = {}
    for actor, config in actors.items():
        fields(config, "key role", f"actor {actor}")
        require(config["role"] in {*KINDS.values(), "recorder"} - {None}, "actor role")
        hexadecimal(config["key"])
        require(config["key"] not in keys.values(), "actors must use distinct keys")
        keys[actor] = config["key"]

    events = bundle["events"]
    checkpoints: dict = {}
    at_count: dict = {}
    for checkpoint in bundle["checkpoints"]:
        fields(checkpoint, "body signature", "checkpoint")
        b = checkpoint["body"]
        fields(b, CHECKPOINT_FIELDS, "checkpoint body")
        require(
            b["domain"] == "TRACE-checkpoint-v1" and b["chain"] == bundle["chain"],
            "checkpoint domain/chain",
        )
        count = integer(b["count"], "checkpoint count", 1)
        require(count <= len(events), "checkpoint exceeds event count")
        identity = digest(checkpoint)
        require(identity not in checkpoints, "duplicate checkpoint")
        checkpoints[identity] = checkpoint
        at_count.setdefault(count, []).append(checkpoint)

    by_id: dict = {}
    previous = None
    appended = 0
    checkpoint_created = 0
    all_keys = set(keys.values())
    revoked_actors: set = set()
    for sequence, event in enumerate(events):
        try:
            fields(event, "body signature", "event")
            b = event["body"]
            fields(b, EVENT_FIELDS, "event body")
            require(
                b["domain"] == "TRACE-event-v1" and b["chain"] == bundle["chain"],
                "event domain/chain",
            )
            require(
                integer(b["sequence"], "sequence") == sequence
                and b["previous"] == previous,
                "sequence/predecessor",
            )
            require(
                isinstance(b["id"], str)
                and 0 < len(b["id"]) <= 200
                and b["id"] not in by_id,
                "duplicate/invalid event id",
            )
            require(
                b["kind"] in KINDS and isinstance(b["payload"], dict),
                "event type/payload",
            )
            require(
                b["actor"] in actors
                and b["actor"] not in revoked_actors
                and b["key"] == keys[b["actor"]],
                "inactive/untrusted actor key",
            )
            role = KINDS[b["kind"]]
            require(
                role is None or actors[b["actor"]]["role"] == role,
                "ineligible actor role",
            )
            verify_signature(b["key"], b, event["signature"])
            integer(b["observed_ns"], "observation time", 1)
            current_append = integer(b["appended_ns"], "append time", 1)
            require(
                max(appended, checkpoint_created) <= current_append
                and b["observed_ns"] <= current_append,
                "local clock order",
            )
            if b["kind"] == "key_rotate":
                fields(b["payload"], "new_key proof", "rotation")
                new_key = b["payload"]["new_key"]
                hexadecimal(new_key)
                require(new_key not in all_keys, "rotated key reused")
                verify_signature(
                    new_key, rotation_message(b, new_key), b["payload"]["proof"]
                )
                all_keys.add(new_key)
                keys[b["actor"]] = new_key
            elif b["kind"] == "key_revoke":
                fields(b["payload"], "actor reason", "key revocation")
                require(
                    b["payload"]["actor"] in actors
                    and b["payload"]["actor"] not in revoked_actors
                    and bool(b["payload"]["reason"]),
                    "invalid key revocation",
                )
                revoked_actors.add(b["payload"]["actor"])
            by_id[b["id"]] = b
            previous = digest(event)
            appended = current_append
            for checkpoint in at_count.get(sequence + 1, []):
                cb = checkpoint["body"]
                require(
                    cb["actor"] in actors
                    and cb["actor"] not in revoked_actors
                    and actors[cb["actor"]]["role"] == "recorder",
                    "checkpoint signer role",
                )
                require(cb["key"] == keys[cb["actor"]], "checkpoint inactive key")
                require(
                    cb["head"] == previous
                    and integer(cb["created_ns"], "checkpoint time", 1)
                    >= max(appended, checkpoint_created),
                    "checkpoint head/time",
                )
                verify_signature(cb["key"], cb, checkpoint["signature"])
                checkpoint_created = cb["created_ns"]
        except (TraceError, TypeError, KeyError) as exc:
            raise TraceError(f"event[{sequence}]: {exc}") from exc

    times: dict = {}
    for identity, receipt in bundle["anchors"].items():
        require(identity in checkpoints, "timestamp for unknown checkpoint")
        if ca is None:
            raise TraceError("TSA CA required for timestamp verification")
        try:
            times[identity] = verify_timestamp(receipt, identity, ca, trust)
            require(
                checkpoints[identity]["body"]["created_ns"]
                <= times[identity]["latest_ns"],
                "checkpoint local time exceeds TSA upper bound",
            )
        except TraceError as exc:
            raise TraceError(f"checkpoint[{identity}]: {exc}") from exc
    if not draft:
        require(
            expected_checkpoint is not None and expected_checkpoint in checkpoints,
            "externally expected checkpoint missing",
        )
        require(
            checkpoints[expected_checkpoint]["body"]["count"] == len(events),
            "terminal truncation/insertion",
        )
        require(
            expected_checkpoint in times,
            "terminal checkpoint lacks independent time evidence",
        )

    def reference(identity: str, before: dict, kind: str | tuple) -> dict:
        require(
            isinstance(identity, str) and identity in by_id,
            f"missing evidence {identity}",
        )
        value = by_id[identity]
        require(value["sequence"] < before["sequence"], "evidence must precede event")
        require(
            value["kind"] in ((kind,) if isinstance(kind, str) else kind),
            "wrong evidence type",
        )
        return value

    def anchor(
        identity: str, before: dict, required_event: dict, token: str | None = None
    ) -> dict:
        require(identity in times, "evidence checkpoint lacks independent timestamp")
        count = checkpoints[identity]["body"]["count"]
        require(
            required_event["sequence"] < count <= before["sequence"],
            "checkpoint outside evidence/event boundary",
        )
        if token is not None:
            require(
                token == times[identity]["receipt_digest"],
                "timestamp receipt dependency mismatch",
            )
        return times[identity]

    def earliest_cover(event: dict) -> dict | None:
        eligible = [
            t
            for identity, t in times.items()
            if checkpoints[identity]["body"]["count"] > event["sequence"]
        ]
        return min(eligible, key=lambda t: t["latest_ns"]) if eligible else None

    forecasts: dict = {}
    outcomes: dict = {}
    scores: set = set()
    used_authorizations: set = set()
    revoked: set = set()
    policy, epoch = trust["policy"], trust["epoch"]
    for event in events:
        b, p = event["body"], event["body"]["payload"]
        kind = b["kind"]
        try:
            if kind == "observation":
                fields(p, "source version data_commitment", kind)
                require(
                    isinstance(p["source"], str)
                    and p["source"]
                    and isinstance(p["version"], str)
                    and p["version"],
                    "observation provenance",
                )
                hexadecimal(p["data_commitment"])
            elif kind == "forecast":
                fields(
                    p, "observation policy commitment target_ns deadline_ns score", kind
                )
                reference(p["observation"], b, "observation")
                hexadecimal(p["commitment"])
                hexadecimal(p["policy"])
                require(p["score"] == "brier-ppm-v1", "unsupported scoring rule")
                require(
                    integer(p["deadline_ns"], "deadline", 1)
                    > integer(p["target_ns"], "target", 1)
                    > b["appended_ns"],
                    "forecast is not locally prospective",
                )
                forecasts[b["id"]] = b
            elif kind == "reveal":
                fields(p, "forecast prediction salt", kind)
                f = reference(p["forecast"], b, "forecast")
                require(b["actor"] == f["actor"], "reveal author mismatch")
                fields(p["prediction"], "probability_ppm", "prediction")
                require(
                    integer(p["prediction"]["probability_ppm"], "probability")
                    <= 1_000_000,
                    "probability range",
                )
                committed = {
                    "observation": f["payload"]["observation"],
                    "policy": f["payload"]["policy"],
                    "target_ns": f["payload"]["target_ns"],
                    "prediction": p["prediction"],
                }
                require(
                    commitment(committed, p["salt"]) == f["payload"]["commitment"],
                    "forecast reveal mismatch",
                )
            elif kind in ("outcome", "missing"):
                fields(
                    p,
                    (
                        "forecast release_ns source value"
                        if kind == "outcome"
                        else "forecast release_ns source reason"
                    ),
                    kind,
                )
                f = reference(p["forecast"], b, "forecast")
                require(f["id"] not in outcomes, "duplicate resolution")
                require(
                    isinstance(p["source"], str) and p["source"],
                    "oracle source required",
                )
                release = integer(p["release_ns"], "oracle release time", 1)
                require(
                    f["payload"]["target_ns"] <= release <= b["observed_ns"],
                    "invalid oracle release boundary",
                )
                require(
                    b["actor"] != f["actor"], "forecaster cannot witness its outcome"
                )
                cover = earliest_cover(f)
                require(
                    cover is not None
                    and cover["latest_ns"] < f["payload"]["target_ns"],
                    "forecast lacks external commitment before target",
                )
                if kind == "missing":
                    require(
                        release > f["payload"]["deadline_ns"] and bool(p["reason"]),
                        "missing outcome declared too early",
                    )
                else:
                    require(
                        type(p["value"]) is int and p["value"] in (0, 1),
                        "binary outcome required",
                    )
                outcomes[f["id"]] = b
            elif kind == "score":
                fields(
                    p,
                    "forecast reveal outcome outcome_checkpoint anchor_digest squared_error",
                    kind,
                )
                f = reference(p["forecast"], b, "forecast")
                reveal = reference(p["reveal"], b, "reveal")
                outcome = reference(p["outcome"], b, "outcome")
                outcome_time = anchor(
                    p["outcome_checkpoint"], b, outcome, p["anchor_digest"]
                )
                require(
                    outcome_time["earliest_ns"] >= outcome["payload"]["release_ns"],
                    "outcome not independently witnessed after claimed release",
                )
                require(
                    reveal["payload"]["forecast"]
                    == outcome["payload"]["forecast"]
                    == f["id"],
                    "score references different forecasts",
                )
                require(f["id"] not in scores, "duplicate score")
                require(
                    b["actor"] not in (f["actor"], outcome["actor"]),
                    "independent evaluator required",
                )
                require(
                    outcome["payload"]["release_ns"] <= f["payload"]["deadline_ns"],
                    "late outcome cannot be scored",
                )
                error = (
                    reveal["payload"]["prediction"]["probability_ppm"]
                    - outcome["payload"]["value"] * 1_000_000
                )
                require(
                    integer(p["squared_error"], "squared error") == error * error,
                    "incorrect Brier score",
                )
                scores.add(f["id"])
            elif kind == "decision":
                fields(p, "policy epoch evidence action", kind)
                require(
                    p["policy"] == policy
                    and type(p["epoch"]) is int
                    and p["epoch"] == epoch,
                    "decision policy/epoch",
                )
                require(
                    isinstance(p["action"], dict) and p["action"],
                    "decision action required",
                )
                require(
                    isinstance(p["evidence"], list)
                    and p["evidence"]
                    and len(set(p["evidence"])) == len(p["evidence"]),
                    "decision evidence",
                )
                for identity in p["evidence"]:
                    evidence = reference(identity, b, ("observation", "score"))
                    if evidence["kind"] == "score":
                        require(
                            forecasts[evidence["payload"]["forecast"]]["payload"][
                                "policy"
                            ]
                            == policy,
                            "evidence policy mismatch",
                        )
            elif kind == "authorization":
                fields(
                    p,
                    "decision subject evidence_checkpoint anchor_digest policy epoch risk_limits valid_from_ns valid_until_ns",
                    kind,
                )
                decision = reference(p["decision"], b, "decision")
                require(
                    p["subject"] in actors
                    and actors[p["subject"]]["role"] == "executor",
                    "authorization subject role",
                )
                require(
                    p["policy"] == decision["payload"]["policy"] == policy
                    and type(p["epoch"]) is int
                    and p["epoch"] == decision["payload"]["epoch"] == epoch,
                    "authorization policy/epoch",
                )
                require(
                    p["risk_limits"] == trust["risk_limits"], "risk limit expansion"
                )
                require(b["actor"] != decision["actor"], "self-authorization")
                evidence = anchor(
                    p["evidence_checkpoint"], b, decision, p["anchor_digest"]
                )
                require(
                    integer(p["valid_until_ns"], "expiry", 1)
                    > integer(p["valid_from_ns"], "validity", 1)
                    >= evidence["latest_ns"],
                    "authorization validity/evidence order",
                )
            elif kind == "authorized_action":
                fields(
                    p,
                    "authorization authorization_checkpoint anchor_digest policy epoch risk_limits",
                    kind,
                )
                auth = reference(p["authorization"], b, "authorization")
                ap = auth["payload"]
                require(b["actor"] == ap["subject"], "authorization subject mismatch")
                decision = reference(ap["decision"], b, "decision")
                require(
                    auth["id"] not in used_authorizations and auth["id"] not in revoked,
                    "used/revoked authorization",
                )
                require(
                    type(p["epoch"]) is int
                    and p["epoch"] == epoch == ap["epoch"]
                    and p["policy"] == policy == ap["policy"],
                    "action policy/epoch",
                )
                require(
                    p["risk_limits"] == ap["risk_limits"] == trust["risk_limits"],
                    "action risk limits",
                )
                require(
                    b["actor"] not in (auth["actor"], decision["actor"]),
                    "action role separation",
                )
                for identity in decision["payload"]["evidence"]:
                    require(
                        by_id[identity]["actor"] != b["actor"],
                        "action author supplied its own evidence",
                    )
                authorization_time = anchor(
                    p["authorization_checkpoint"], b, auth, p["anchor_digest"]
                )
                require(
                    authorization_time["earliest_ns"] >= ap["valid_from_ns"],
                    "authorization not yet valid",
                )
                covering = earliest_cover(b)
                if covering is None:
                    require(draft, "action lacks external execution-record checkpoint")
                    upper = b["appended_ns"]
                else:
                    upper = covering["latest_ns"]
                require(upper <= ap["valid_until_ns"], "authorization expired")
                evidence_time = times[ap["evidence_checkpoint"]]
                require(
                    upper - evidence_time["earliest_ns"]
                    <= trust["max_evidence_age_ns"],
                    "stale governance evidence",
                )
                used_authorizations.add(auth["id"])
            elif kind == "epoch":
                fields(p, "policy epoch reason", kind)
                hexadecimal(p["policy"])
                require(
                    type(p["epoch"]) is int
                    and p["epoch"] == epoch + 1
                    and p["reason"] in ("promote", "rollback", "retire"),
                    "invalid epoch transition",
                )
                epoch, policy = p["epoch"], p["policy"]
            elif kind == "revoke":
                fields(p, "authorization reason", kind)
                reference(p["authorization"], b, "authorization")
                require(
                    p["authorization"] not in revoked and bool(p["reason"]),
                    "duplicate/invalid revocation",
                )
                revoked.add(p["authorization"])
        except (TraceError, TypeError, KeyError) as exc:
            raise TraceError(f"event[{b['sequence']}] {kind}: {exc}") from exc

    status = {}
    if not draft:
        for resolved in outcomes.values():
            cover = earliest_cover(resolved)
            require(
                cover is not None
                and cover["earliest_ns"] >= resolved["payload"]["release_ns"],
                f"outcome {resolved['id']}: no independent witness after release",
            )
    for identity, f in forecasts.items():
        resolution = outcomes.get(identity)
        if identity in scores:
            status[identity] = "scored"
        elif resolution:
            status[identity] = (
                "missing"
                if resolution["kind"] == "missing"
                else (
                    "late"
                    if resolution["payload"]["release_ns"] > f["payload"]["deadline_ns"]
                    else "unscored"
                )
            )
        else:
            last_time = (
                times.get(expected_checkpoint, {}) if expected_checkpoint else {}
            )
            status[identity] = (
                "overdue_without_resolution"
                if last_time.get("earliest_ns", 0) > f["payload"]["deadline_ns"]
                else "pending"
            )
    return {
        "valid": True,
        "draft": draft,
        "chain": bundle["chain"],
        "events": len(events),
        "checkpoint": expected_checkpoint,
        "independent_time": bool(times) and not draft,
        "timestamps": times,
        "forecast_status": status,
        "authorized_actions": len(used_authorizations),
        "policy": policy,
        "epoch": epoch,
        "limitations": [
            "Oracle release assertions depend on independently configured oracle trust.",
            "Recorded authorization is not proof of broker execution or realized performance.",
            "Offline certificate validation does not fetch current revocation status.",
        ],
    }
