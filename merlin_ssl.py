import ssl
import os
from pathlib import Path
from merlin_logger import merlin_logger


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
    # Placeholder for generating self-signed certs using cryptography lib
    pass
