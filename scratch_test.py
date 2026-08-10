import urllib.request
import json

url = "https://web-production-c16ea.up.railway.app/send_email"
headers = {
    "Authorization": "Bearer saiprasad@13",
    "X-API-Key": "saiprasad@13",
    "Content-Type": "application/json"
}
payload = json.dumps({"to": "test@example.com", "subject": "test", "body": "test"}).encode()

req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
try:
    with urllib.request.urlopen(req) as response:
        print(response.getcode(), response.read().decode())
except Exception as e:
    print("Error:", e)
