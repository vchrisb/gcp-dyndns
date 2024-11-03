# gcp-dyndns

Dyndns for Google Cloud DNS implemented using a Google functions

Currently only Googld Domains does provide an option to update a record with a dyndns client. This function implemets a dyndns compatible endpoint to update a DNS record in Google Cloud DNS

Parameters:
* `DYNDNS_USERNAME`: username for basic auth authentication
* `DYNDNS_PASSWORD`: password hash for basic auth authentication
* `DNS_ZONE`: Google Cloud DNS Zone name where the record will be managed
* `DNS_HOSTNAME`: DNS name to be updated, to restrict the function for security concerns
* `DNS_TTL`: Optional TTL value for record in seconds. Default is 5 minutes.
* `GCP_PROJECT`: Project to be used

### Deploy to google functions

```
gcloud functions deploy dyndns --entry-point update_dns --runtime python312 --trigger-http --allow-unauthenticated --set-env-vars DYNDNS_USERNAME=<username>,DYNDNS_PASSWORD=<password_hash>,DNS_ZONE=<zone name>,DNS_HOSTNAME=<hostname>,DNS_TTL=<ttl>,GCP_PROJECT=<gcp_project>
```

### access function

The function URL has the format `https://<region>-<project-id>.cloudfunctions.net/dyndns`.
It can by access by `https://<region>-<project-id>.cloudfunctions.net/dyndns?myip=<ip address>&hostname=<hostname>`
Only the parameter are important. 
The URL can also be e.g. `https://<region>-<project-id>.cloudfunctions.net/dyndns/nic/update?system=dyndns&?myip=<ip address>&hostname=<hostname>` or `https://<region>-<project-id>.cloudfunctions.net/dyndns/v3/update&?myip=<ip address>&hostname=<hostname>`

### tested with Ubiquity USG

This setup runs succefully with configuring Unifi USG in Unifi Controller under `Settings -> Services -> Dynamic DNS` with  
* Service: `dyndns`
* Hostname: `host.domain.com`
* Username: `username`
* Password: `password`
* Server: `<region>-<project-id>.cloudfunctions.net/dyndns`

### Troubleshoot

```
gcloud functions logs read dyndns
```

### generate compatible password hash

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 password_hash.py <password>
```
