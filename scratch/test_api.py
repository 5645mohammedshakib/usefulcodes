import urllib.request
import ssl
import json

ctx = ssl.create_default_context()
data = json.dumps({'email': 'mohammedshakib663', 'password': 'MOHDshakib@123'}).encode()
req = urllib.request.Request('https://hub-6yrl.onrender.com/api/auth/login', data=data, headers={'Content-Type':'application/json'}, method='POST')
token = json.loads(urllib.request.urlopen(req, timeout=30, context=ctx).read().decode())['token']

boundary = 'Boundary123'
body = (
    b'--Boundary123\r\n'
    b'Content-Disposition: form-data; name="title"\r\n\r\n'
    b'Test Note\r\n'
    b'--Boundary123\r\n'
    b'Content-Disposition: form-data; name="description"\r\n\r\n'
    b'Test Desc\r\n'
    b'--Boundary123\r\n'
    b'Content-Disposition: form-data; name="category"\r\n\r\n'
    b'General\r\n'
    b'--Boundary123--\r\n'
)

req = urllib.request.Request(
    'https://hub-6yrl.onrender.com/api/notes',
    data=body,
    headers={
        'Content-Type': 'multipart/form-data; boundary=Boundary123',
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
