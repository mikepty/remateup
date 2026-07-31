import sqlite3
db = sqlite3.connect(r"backend\data\remateup.db")
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
for t in tables:
    cols = [f"{c[1]}:{c[2]}" for c in db.execute(f"PRAGMA table_info(\"{t}\")").fetchall()]
    print(f"  {t}: {cols}")
db.close()
