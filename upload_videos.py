import os
import urllib.request
from urllib.error import HTTPError

supabase_url = 'https://vgzojsbmmvptfhdrfsko.supabase.co'
anon_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnem9qc2JtbXZwdGZoZHJmc2tvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM4MTYxMzgsImV4cCI6MjA5OTM5MjEzOH0.rzAHm51EHiblECnR-aY3QmM4kH_laJXhkx2SeSsyeEM'

files = ['Vertical.mp4', 'videoplayback.mp4']

for filename in files:
    path = os.path.join('static', filename)
    if not os.path.exists(path):
        print(f"File {path} does not exist!")
        continue
        
    print(f"Uploading {filename} ({os.path.getsize(path) / 1024 / 1024:.2f} MB)...")
    with open(path, 'rb') as f:
        file_data = f.read()
        
    url = f"{supabase_url}/storage/v1/object/public-assets/{filename}"
    
    req = urllib.request.Request(
        url,
        data=file_data,
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "video/mp4",
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Successfully uploaded {filename}!")
    except HTTPError as e:
        print(f"Error uploading {filename}: {e.code} {e.reason}")
        print(e.read().decode('utf-8'))
