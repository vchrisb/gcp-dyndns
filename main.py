import ipaddress
import logging
import re

import functions_framework
import google.cloud.logging
from flask import Request
from flask.typing import ResponseReturnValue
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash

from dyndns_service import Config, DNSUpdater, DynDNSResponse

# Instantiates a client
client = google.cloud.logging.Client()

# Retrieves a Cloud Logging handler based on the environment
# you're running in and integrates the handler with the
# Python logging module. By default this captures all logs
# at INFO level and higher
client.setup_logging()

# Configure logging for Google Cloud Functions
logger = logging.getLogger()

# Log initialization
logger.info("Initializing DynDNS service...")

auth = HTTPBasicAuth()
config = Config.from_env()
dns_updater = DNSUpdater(config)


def is_valid_fqdn(hostname: str) -> bool:
    """Validate if a hostname is a valid FQDN"""
    if not hostname or len(hostname) > 253:
        return False

    hostname_regex = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}$")
    return bool(hostname_regex.match(hostname))


@auth.verify_password
def verify_password(username: str, password: str) -> bool:
    """Verify request authentication"""
    try:
        if username != config.username:
            return False
        return check_password_hash(config.password_hash, password)
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return False


@auth.error_handler
def auth_error() -> ResponseReturnValue:
    """Handle authentication errors with WWW-Authenticate header"""
    headers = {"WWW-Authenticate": 'Basic realm="DynDNS Update Service"'}
    return DynDNSResponse.BADAUTH.to_response(headers=headers)


@functions_framework.http
@auth.login_required
def update_dns(request: Request) -> ResponseReturnValue:
    """Google Cloud Function entry point"""

    # Log incoming request
    logger.info(f"Received {request.method} request from {request.remote_addr}")

    # Standard CORS headers for all responses
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "3600",
    }

    try:
        # Handle OPTIONS request for CORS preflight
        if request.method == "OPTIONS":
            logger.info("Handling OPTIONS request")
            return "", 204, cors_headers

        # Extract and validate hostname
        hostname = request.args.get("hostname")
        if not hostname:
            return DynDNSResponse.NOHOST.to_response()

        if not is_valid_fqdn(hostname):
            return DynDNSResponse.NOTFQDN.to_response()

        if not dns_updater.validate_hostname(hostname):
            return DynDNSResponse.NOHOST.to_response()

        # Extract and validate IP
        myip = request.args.get("myip")
        try:
            ip_obj = ipaddress.ip_address(myip)
            if not isinstance(ip_obj, ipaddress.IPv4Address):
                return DynDNSResponse.BADIP.to_response()
        except (ValueError, AttributeError):
            return DynDNSResponse.BADIP.to_response()

        # Update DNS
        if dns_updater.update_record(myip):
            return DynDNSResponse.GOOD.to_response()
        return DynDNSResponse.DNSERR.to_response()

    except Exception as e:
        logger.error(f"Error handling request: {str(e)}")
        return DynDNSResponse.INTERNAL_ERROR.to_response()
