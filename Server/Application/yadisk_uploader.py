import os
import requests

API_BASE = "https://cloud-api.yandex.net/v1/disk"

def get_headers(access_token):
    return {
        "Authorization": f"OAuth {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def test_connection(access_token):
    url = f"{API_BASE}/"
    response = requests.get(url, headers=get_headers(access_token))
    return response.status_code == 200

def get_upload_link(remote_path, access_token):
    url = f"{API_BASE}/resources/upload"
    params = {"path": remote_path, "overwrite": "true"}
    response = requests.get(url, headers=get_headers(access_token), params=params)
    if response.status_code == 200:
        return response.json().get("href")
    return None

def upload_file(local_path, remote_path, access_token):
    upload_url = get_upload_link(remote_path, access_token)
    if not upload_url:
        return False
    
    with open(local_path, 'rb') as f:
        response = requests.put(upload_url, files={"file": f})
    
    return response.status_code == 201

def create_folder(folder_path, access_token):
    url = f"{API_BASE}/resources"
    params = {"path": folder_path}
    response = requests.put(url, headers=get_headers(access_token), params=params)
    return response.status_code in [201, 409]