import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple

from google.api_core import exceptions as google_exceptions
from google.api_core import retry
from google.cloud import dns

# Configure logging for Google Cloud Functions
logger = logging.getLogger()


class DynDNSResponse(Enum):
    """Standardized DynDNS protocol responses with detailed messages"""

    GOOD = ("good", 200, "Update successful")
    NOHOST = ("nohost", 400, "Hostname not found or not authorized")
    NOTFQDN = ("notfqdn", 400, "Invalid hostname format")
    BADIP = ("badip", 400, "Invalid IP address format")
    DNSERR = ("dnserr", 500, "DNS update failed")
    BADAUTH = ("badauth", 401, "Authentication failed")
    INTERNAL_ERROR = ("911", 500, "Internal server error")

    def __init__(self, code: str, status_code: int, description: str):
        self.code = code
        self.status_code = status_code
        self.description = description

    def to_response(self, include_description: bool = False, headers: Dict = {}) -> Tuple[Dict[str, str], int, Dict]:
        """Return a structured response with optional description and headers"""
        response = {"status": self.code}
        if include_description:
            response["description"] = self.description
        return response, self.status_code, {"Access-Control-Allow-Origin": "*"} | headers


@dataclass
class Config:
    """Configuration settings for the DynDNS service"""

    username: str
    password_hash: str
    hostname: str
    zone: str
    project_id: str
    ttl: int = field(default=300)
    max_retries: int = field(default=3)
    retry_delay: int = field(default=1)

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables with validation"""
        try:
            required_vars = {
                "DYNDNS_USERNAME": "username",
                "DYNDNS_PASSWORD": "password_hash",
                "DNS_HOSTNAME": "hostname",
                "DNS_ZONE": "zone",
            }

            config_dict = {}

            # Validate required environment variables
            missing_vars = []
            for env_var, config_key in required_vars.items():
                value = os.environ.get(env_var)
                if not value:
                    missing_vars.append(env_var)
                config_dict[config_key] = value

            if missing_vars:
                raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

            # Handle optional variables with defaults
            config_dict["ttl"] = int(os.getenv("DNS_TTL", 300))
            config_dict["max_retries"] = int(os.getenv("MAX_RETRIES", 3))
            config_dict["retry_delay"] = int(os.getenv("RETRY_DELAY", 1))

            # Handle project ID with fallback
            project_id = os.getenv("PROJECT_ID") or os.getenv("GCP_PROJECT")
            if not project_id:
                raise ValueError("Environment Variable PROJECT_ID or GCP_PROJECT needs to be specified")
            config_dict["project_id"] = project_id

            return cls(**config_dict)
        except Exception as e:
            logger.error(f"Configuration error: {str(e)}")
            raise


class DNSUpdater:
    """Handles DNS record updates in Google Cloud DNS"""

    def __init__(self, config: Config):
        self.config = config
        self.client = dns.Client(project=config.project_id)
        self.zone = self.client.zone(config.zone)
        self._validate_zone()

    def _validate_zone(self) -> None:
        """Validate zone exists during initialization"""
        if not self.zone.exists():
            raise ValueError(f"DNS zone '{self.config.zone}' does not exist")

    def validate_hostname(self, hostname: str) -> bool:
        """Validate if hostname matches configured hostname"""
        return hostname.lower() == self.config.hostname.lower()

    @retry.Retry(
        predicate=retry.if_exception_type(
            google_exceptions.RetryError,
            google_exceptions.ServerError,
            google_exceptions.ServiceUnavailable,
            google_exceptions.InternalServerError,
        ),
        initial=1.0,
        maximum=60.0,
        multiplier=2.0,
    )
    def update_record(self, ip_address: str) -> bool:
        """Update DNS record with exponential backoff retry capability"""
        try:
            hostname = f"{self.config.hostname}."
            changes = self.zone.changes()

            # Find existing record
            record_old = self._get_existing_record(hostname)

            if record_old and record_old.rrdatas[0] == ip_address:
                logger.info(f"Record {hostname} with IP {ip_address} already exists -> skipping")
                return True

            # Create new record
            record_new = self.zone.resource_record_set(hostname, "A", self.config.ttl, [ip_address])

            # Apply changes
            if record_old:
                logger.info(f"Updating existing record {hostname} from {record_old.rrdatas[0]} to {ip_address}")
                changes.delete_record_set(record_old)
            else:
                logger.info(f"Creating new record {hostname} with IP {ip_address}")

            changes.add_record_set(record_new)
            changes.create()

            return True
        except Exception as e:
            logger.error(f"Failed to update DNS record: {str(e)}")
            raise

    def _get_existing_record(self, hostname: str) -> Optional[dns.resource_record_set.ResourceRecordSet]:
        """Find existing A record for hostname"""
        try:
            for record in self.zone.list_resource_record_sets():
                if record.name == hostname and record.record_type == "A":
                    return record
            return None
        except google_exceptions.GoogleAPIError as e:
            logger.error(f"Error fetching DNS records: {str(e)}")
            raise
