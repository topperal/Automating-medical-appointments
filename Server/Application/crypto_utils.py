import json
import base64
import os
import hashlib
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

def encrypt_json(json_filename, room_id, secret_key, delete_original=True):
    if not secret_key:
        raise ValueError("Секретный ключ не задан")
    if not os.path.exists(json_filename):
        raise FileNotFoundError(f"Файл {json_filename} не найден")
    
    key = hashlib.sha256((room_id + secret_key).encode()).digest()
    iv = os.urandom(16)
    
    with open(json_filename, 'rb') as f:
        plaintext = f.read()
    
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(plaintext, AES.block_size))
    
    metadata = json.dumps({
        "room_id": room_id,
        "time": datetime.now().isoformat()
    }).encode()
    
    result = len(metadata).to_bytes(2, 'big') + metadata + iv + encrypted
    
    output_file = f"room-{room_id}.json.enc"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(base64.b64encode(result).decode())
    
    if delete_original:
        os.remove(json_filename)
    
    return output_file