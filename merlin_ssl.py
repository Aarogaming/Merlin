import ssl
from pathlib import Path
from merlin_logger import merlin_logger
from merlin_utils import generate_self_signed_cert as _generate_self_signed_cert


def get_ssl_context():
    # Task 6: Add support for HTTPS/TLS
    cert_file = Path("certs/cert.pem")
    key_file = Path("certs/key.pem")

    if cert_file.exists() and key_file.exists():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        merlin_logger.info("SSL context loaded.")
        return context
    else:
        merlin_logger.warning("SSL certificates not found. Running in HTTP mode.")
        return None


def generate_self_signed_cert():
    certs_dir = Path("certs")
    certs_dir.mkdir(parents=True, exist_ok=True)
    cert_file = certs_dir / "cert.pem"
    key_file = certs_dir / "key.pem"

    try:
        _generate_self_signed_cert(str(cert_file), str(key_file))
        merlin_logger.info("Generated self-signed TLS certificate bundle")
        return str(cert_file), str(key_file)
    except Exception as exc:  # noqa: BLE001
        merlin_logger.error(f"Failed generating self-signed certs: {exc}")
        return None
