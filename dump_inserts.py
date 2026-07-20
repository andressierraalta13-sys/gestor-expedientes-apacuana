import sqlite3
import re

con = sqlite3.connect('db.sqlite3')
with open('inserts.sql', 'w', encoding='utf-8') as f:
    for line in con.iterdump():
        if line.startswith('INSERT INTO '):
            # Postgres syntax is similar, but we need to ensure double quotes for identifiers
            # Actually sqlite iterdump quotes tables with "table_name" which is PERFECT for postgres.
            # Booleans are dumped as 0 or 1, which might need casting, but postgres usually accepts integer 0/1 for booleans if not strictly typed, wait, Postgres STRICT boolean requires 'true'/'false'.
            # But let's just dump and see what it looks like.
            f.write(line + '\n')
