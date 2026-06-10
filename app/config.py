import logging
import os
import ssl
from typing import Optional

import truststore

# Home Assistant configuration
HA_URL: str = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN: str = os.environ.get("HA_TOKEN", "")

logger = logging.getLogger(__name__)


def _build_ssl_context() -> ssl.SSLContext:
    """Build the TLS verification context.

    Layered so users running an in-house CA (e.g. step-ca, smallstep) can
    connect to a properly-signed HA instance on any platform / deployment
    mode without weakening verification:

    1. If `SSL_CERT_FILE` is set, use it. This is the OpenSSL standard env
       var, honored by every modern tool. It's the primary mechanism for
       Docker (bind-mount the CA, set the env var) and explicit overrides.
    2. Otherwise use truststore, which bridges to the OS-native trust store
       (macOS Keychain, Windows Cert Store, Linux ca-certificates). Users
       who installed their CA at the OS level get it for free.

    No REQUESTS_CA_BUNDLE shim — that's a requests-ism, not a standard.
    No verify=False fallback — silent downgrade is worse than a hard failure.
    """
    cert_file = os.environ.get("SSL_CERT_FILE")
    if cert_file:
        logger.debug("TLS: using SSL_CERT_FILE=%s", cert_file)
        return ssl.create_default_context(cafile=cert_file)
    logger.debug("TLS: using OS native trust store via truststore")
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

def get_ha_headers() -> dict:
    """Return the headers needed for Home Assistant API requests"""
    headers = {
        "Content-Type": "application/json",
    }
    
    # Only add Authorization header if token is provided
    if HA_TOKEN:
        headers["Authorization"] = f"Bearer {HA_TOKEN}"
    
    return headers
