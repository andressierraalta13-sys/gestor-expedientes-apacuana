import os
import django
import json
import urllib.request
from urllib.error import HTTPError

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.apps import apps
from django.db import models

supabase_url = 'https://vgzojsbmmvptfhdrfsko.supabase.co/rest/v1'
anon_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnem9qc2JtbXZwdGZoZHJmc2tvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM4MTYxMzgsImV4cCI6MjA5OTM5MjEzOH0.rzAHm51EHiblECnR-aY3QmM4kH_laJXhkx2SeSsyeEM'

with open('db_dump_raw.json', encoding='utf-16') as f:
    data = json.load(f)

# Group rows sequentially to preserve topological order
blocks = []
last_model = None
for row in data:
    model_name = row['model']
    if model_name != last_model:
        blocks.append((model_name, []))
        last_model = model_name
    blocks[-1][1].append(row)

total_records = 0
for model_name, rows in blocks:
    try:
        model = apps.get_model(model_name)
    except Exception as e:
        print(f"Skipping {model_name}: {e}")
        continue
    
    db_table = model._meta.db_table
    pk_attname = model._meta.pk.attname
    
    payloads = []
    for row in rows:
        record = {}
        # PK
        if 'pk' in row and row['pk'] is not None:
            record[pk_attname] = row['pk']
            
        # Fields
        for k, v in row['fields'].items():
            try:
                field = model._meta.get_field(k)
                if not field.concrete or field.many_to_many:
                    continue
                record[field.attname] = v
            except Exception:
                pass
        payloads.append(record)
        
    print(f"Inserting {len(payloads)} records into {db_table}...")
    
    # Send in batches of 1000
    batch_size = 1000
    for i in range(0, len(payloads), batch_size):
        batch = payloads[i:i+batch_size]
        
        req = urllib.request.Request(
            f"{supabase_url}/{db_table}?on_conflict={pk_attname}",
            data=json.dumps(batch).encode('utf-8'),
            headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {anon_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates"
            },
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                total_records += len(batch)
        except HTTPError as e:
            err = e.read().decode('utf-8')
            if 'duplicate key value' in err:
                print(f"  -> {db_table} batch already exists or partially inserted.")
            else:
                print(f"Error on {db_table}: {e.code} {e.reason}")
                print(err)

print(f"Importacion finalizada. Registros insertados: {total_records}")
