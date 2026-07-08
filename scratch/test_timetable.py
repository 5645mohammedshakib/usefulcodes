import urllib.request
import ssl
import json

ctx = ssl.create_default_context()
data = json.dumps({'email': 'mohammedshakib663', 'password': 'MOHDshakib@123'}).encode()
req = urllib.request.Request('https://hub-6yrl.onrender.com/api/auth/login', data=data, headers={'Content-Type':'application/json'}, method='POST')
token = json.loads(urllib.request.urlopen(req, timeout=30, context=ctx).read().decode())['token']

tt_data = {
    "title": "Test Class Timetable",
    "slots": [
        {
            "day": "Monday",
            "subject": "Mathematics",
            "start": "09:00",
            "end": "10:00",
            "location": "Room 101"
        }
    ]
}

req = urllib.request.Request(
    'https://hub-6yrl.onrender.com/api/timetable',
    data=json.dumps(tt_data).encode(),
    headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
    },
    method='POST'
)

try:
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        print('STATUS:', r.status, r.read().decode())
except urllib.error.HTTPError as e:
    print('HTTP', e.code, e.read().decode())
except Exception as e:
    print('ERROR:', str(e))
