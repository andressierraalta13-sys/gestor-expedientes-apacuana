import os
import json
import urllib.request
from urllib.error import HTTPError
import re

supabase_url = 'https://vgzojsbmmvptfhdrfsko.supabase.co'
anon_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnem9qc2JtbXZwdGZoZHJmc2tvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM4MTYxMzgsImV4cCI6MjA5OTM5MjEzOH0.rzAHm51EHiblECnR-aY3QmM4kH_laJXhkx2SeSsyeEM'

with open('schema_postgres_clean.sql', 'r', encoding='utf-8') as f:
    content = f.read()

migrations = content.split('-- MIGRATION: ')
for i, m in enumerate(migrations):
    if not m.strip():
        continue
    
    parts = m.split('\n', 1)
    name = parts[0].strip()
    if len(parts) > 1:
        sql = parts[1].strip()
    else:
        continue
        
    # Remove BEGIN; and COMMIT;
    sql = re.sub(r'^BEGIN;\s*', '', sql)
    sql = re.sub(r'\s*COMMIT;\s*$', '', sql)
    
    # Some schemas have extra BEGIN; or COMMIT; inside
    sql = sql.replace('BEGIN;', '').replace('COMMIT;', '')
    
    if not sql or sql.strip() == '' or '(no-op)' in sql and len(sql.splitlines()) < 10:
        # Check if it's just comments
        lines = [l for l in sql.splitlines() if l.strip() and not l.strip().startswith('--')]
        if not lines:
            print(f"[{i}/{len(migrations)-1}] Skipping {name} (no-op)")
            continue

    print(f"[{i}/{len(migrations)-1}] Executing {name}...")
    
    req = urllib.request.Request(
        f"{supabase_url}/rest/v1/rpc/run_migration",
        data=json.dumps({"sql_string": sql}).encode('utf-8'),
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res = response.read()
    except HTTPError as e:
        error_body = e.read().decode('utf-8')
        if 'already exists' in error_body or 'does not exist' in error_body:
            print(f"  -> Objeto ya existe o no existe, omitiendo error.")
        else:
            print(f"Error on {name}: {e.code} {e.reason}")
            print(error_body)
            # break # continue on errors

print("Migracion de esquema finalizada.")
