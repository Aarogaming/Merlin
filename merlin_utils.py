import os
import random
import ssl
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, TypeVar
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

T = TypeVar("T")


def stable_claim_hash(text: str) -> str:
    normalized_text = " ".join(str(text).strip().lower().split())
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RetryBackoffPolicy:
    max_attempts: int = 1
    initial_backoff_seconds: float = 0.1
    max_backoff_seconds: float = 1.0
    jitter_ratio: float = 0.2
    retry_budget_seconds: float | None = None


def compute_retry_backoff_seconds(
    retry_index: int,
    *,
    policy: RetryBackoffPolicy,
    random_fn: Callable[[], float] = random.random,
) -> float:
    if retry_index < 0:
        retry_index = 0

    base_delay = policy.initial_backoff_seconds * (2**retry_index)
    capped_delay = min(max(0.0, policy.max_backoff_seconds), max(0.0, base_delay))
    jitter_ratio = max(0.0, min(1.0, policy.jitter_ratio))
    if jitter_ratio == 0.0:
        return capped_delay

    jitter_span = capped_delay * jitter_ratio
    lower_bound = max(0.0, capped_delay - jitter_span)
    upper_bound = capped_delay + jitter_span
    sample = max(0.0, min(1.0, float(random_fn())))
    return lower_bound + ((upper_bound - lower_bound) * sample)


def retry_with_backoff(
    operation: Callable[[], T],
    *,
    policy: RetryBackoffPolicy,
    should_retry: Callable[[Exception], bool],
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    random_fn: Callable[[], float] = random.random,
    on_retry: Callable[[int, float, Exception], None] | None = None,
) -> T:
    max_attempts = max(1, int(policy.max_attempts))
    retry_budget = (
        None
        if policy.retry_budget_seconds is None
        else max(0.0, float(policy.retry_budget_seconds))
    )
    started_at = monotonic_fn()

    for attempt_index in range(max_attempts):
        try:
            return operation()
        except Exception as error:
            if attempt_index >= max_attempts - 1:
                raise
            if not should_retry(error):
                raise

            delay = compute_retry_backoff_seconds(
                attempt_index,
                policy=policy,
                random_fn=random_fn,
            )
            if retry_budget is not None:
                elapsed = max(0.0, monotonic_fn() - started_at)
                remaining_budget = retry_budget - elapsed
                if remaining_budget <= 0.0:
                    raise
                delay = min(delay, remaining_budget)
                if delay <= 0.0:
                    raise

            next_attempt = attempt_index + 2
            if on_retry is not None:
                on_retry(next_attempt, delay, error)
            if delay > 0.0:
                sleep_fn(delay)

    raise RuntimeError("retry_with_backoff exhausted unexpectedly")


def generate_self_signed_cert(cert_file="merlin.crt", key_file="merlin.key"):
    if os.path.exists(cert_file) and os.path.exists(key_file):
        return

    # Generate key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Generate cert
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Merlin Merlin"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Write key
    with open(key_file, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    # Write cert
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


def update_env_file(key: str, value: str):
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break

    if not found:
        lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)
