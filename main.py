from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from google.cloud import dns
import os
import ipaddress
from sys import exit

auth = HTTPBasicAuth()

if 'DYNDNS_USERNAME' in os.environ:
  dyndns_username = os.environ.get('DYNDNS_USERNAME')
else:
  raise Exception("Environment Variable DYNDNS_USERNAME needs to be specified")

if 'DYNDNS_PASSWORD' in os.environ:
  dyndns_password = os.environ.get('DYNDNS_PASSWORD')
else:
  raise Exception("Environment Variable DYNDNS_PASSWORD needs to be specified")

if 'DNS_HOSTNAME' in os.environ:
  DNS_HOSTNAME = os.environ.get('DNS_HOSTNAME')
else:
  raise Exception("Environment Variable DNS_HOSTNAME needs to be specified")

if 'DNS_ZONE' in os.environ:
  dns_zone = os.environ.get('DNS_ZONE')
else:
  raise Exception("Environment Variable DNS_ZONE needs to be specified")

if 'DNS_TTL' in os.environ:
  dns_ttl = os.getenv('DNS_TTL')
else:
  dns_ttl = 5 * 60  # 5 minute default

if 'PROJECT_ID' in os.environ:
  project_id = os.getenv('PROJECT_ID')
elif 'GCP_PROJECT' in os.environ:
  project_id = os.getenv('GCP_PROJECT')
else:
  raise Exception("Environment Variable PROJECT_ID or GCP_PROJECT needs to be specified")


@auth.verify_password
def verify_password(username, password):
  if username == dyndns_username:
    return check_password_hash(dyndns_password, password)
  return False

@auth.login_required
def dyndns(request):
  myip = request.args.get('myip')
  ipaddress.ip_address(myip)
  hostname = request.args.get('hostname')
  username = auth.username()
  print (f"Request Url: {request.url}")
  #print(f"{project_id}")
  print(f"Request Proto: {request.headers.get('X-Forwarded-Proto')}")
  print(f"Updating with IP: {myip}, Hostname: {hostname}, User: {username}")
  if update_dns(hostname, myip):
    return ('success', 200)
  else:
    return ('error', 500)

def update_dns(hostname, myip):
  client = dns.Client(project=project_id)
  zone = client.zone(dns_zone)
  record_old = None
  if not zone.exists():
    print(f"Zone with name: {dns_zone} does not exist!")
    return False
  if hostname == DNS_HOSTNAME:
    hostname = hostname + "."
  else:
    print(f"Provided Hostname: {hostname} does not equal {DNS_HOSTNAME}!")
    return False
  resource_record_sets = zone.list_resource_record_sets()
  for record in resource_record_sets:
    if record.name == hostname and record.record_type == 'A':
      record_old = record
      if record_old.rrdatas[0] == myip:
        print(f"Record {hostname} with IP {myip} already exists -> skipping")
        return True
      else:
        print(f"Record {hostname} does exists with different IP -> updating")
  record_new = zone.resource_record_set(hostname, 'A', dns_ttl, [myip,])
  changes = zone.changes()
  if not record_old is None:
    changes.delete_record_set(record_old)
  changes.add_record_set(record_new)
  changes.create()
  return True
