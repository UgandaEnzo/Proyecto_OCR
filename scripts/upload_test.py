import requests
import os
import base64

URL = 'http://127.0.0.1:8000/subir-pago/'
THIS_DIR = os.path.dirname(os.path.dirname(__file__))
IMG_PATH = os.path.join(THIS_DIR, 'scripts', 'sample.png')

# PNG de 1x1 generado en base64 (bytes correctos)
SAMPLE_B64 = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAl8B9Wb0z1kAAAAASUVORK5CYII='

with open(IMG_PATH, 'wb') as f:
    f.write(base64.b64decode(SAMPLE_B64))

def subir():
    with open(IMG_PATH, 'rb') as f:
        files = {'file': ('sample.png', f, 'image/png')}
        r = requests.post(URL, files=files)
        print('Status:', r.status_code)
        print('Body:', r.text)

print('Primera subida:')
subir()
print('Segunda subida (debe detectar duplicado):')
subir()
