import pandas as pd
import pymysql
import numpy as np
import time

DB_HOST = ""
DB_PORT = 0
DB_USER = ""
DB_PASS = ""
DB_NAME = ""

def get_conn():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4", connect_timeout=30,
        read_timeout=60, write_timeout=60
    )

def safe_int(val):
    if pd.isna(val) or str(val).strip() == '' or str(val) == 'nan':
        return None
    return int(val)

def safe_str(val):
    if pd.isna(val) or str(val).strip() == '' or str(val) == 'nan':
        return None
    return str(val).strip()

def upload_rows(table_name, rows, columns, truncate=True):
    if not rows:
        print(f"  skip {table_name}: no data")
        return

    conn = get_conn()
    cursor = conn.cursor()

    if truncate:
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            cursor.execute(f"TRUNCATE TABLE `{table_name}`")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            conn.commit()
            print(f"  truncated {table_name}")
        except Exception as e:
            try:
                cursor.execute(f"DELETE FROM `{table_name}`")
                conn.commit()
                print(f"  deleted {table_name}")
            except Exception as e2:
                print(f"  truncate failed: {e2}")

    placeholders = ", ".join(["%s"] * len(columns))
    columns_str = ", ".join([f"`{c}`" for c in columns])
    insert_sql = f"INSERT INTO `{table_name}` ({columns_str}) VALUES ({placeholders})"

    total = len(rows)
    inserted = 0
    failed = 0

    for i, values in enumerate(rows):
        for attempt in range(3):
            try:
                cursor.execute(insert_sql, values)
                inserted += 1
                break
            except pymysql.MySQLError as e:
                err_str = str(e)
                if "2006" in err_str or "2013" in err_str or "Lost connection" in err_str or "2003" in err_str:
                    try:
                        cursor.close()
                        conn.close()
                    except:
                        pass
                    time.sleep(3)
                    conn = get_conn()
                    cursor = conn.cursor()
                    continue
                else:
                    failed += 1
                    if failed <= 5:
                        print(f"    row {i} failed: {e}")
                    break
        else:
            failed += 1

        if inserted % 50 == 0:
            try:
                conn.commit()
            except:
                conn = get_conn()
                cursor = conn.cursor()
            print(f"    progress: {inserted + failed}/{total}")

    try:
        conn.commit()
    except:
        pass

    try:
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        count = cursor.fetchone()[0]
        print(f"  done {table_name}: {count} rows (inserted:{inserted}, failed:{failed})")
    except:
        print(f"  done {table_name}: inserted:{inserted}, failed:{failed}")

    cursor.close()
    conn.close()

BASE = r"e:\软工\daduhui"

# ============================================================
# 1. museums — REPLACE (id=1)
# ============================================================
print("=" * 50)
print("1/6 upload museums (REPLACE)")
df = pd.read_csv(f"{BASE}/museums.csv")
conn = get_conn()
cursor = conn.cursor()
for _, r in df.iterrows():
    mid = int(r["id"])
    cursor.execute(
        "REPLACE INTO museums (id, name, short_name, country, city, website, collection_url, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (mid, r["name"], r["short_name"], r["country"], r["city"], r["website"], r["collection_url"], r["created_at"], r["updated_at"])
    )
conn.commit()
cursor.execute("SELECT COUNT(*) FROM museums")
print(f"  done museums: {cursor.fetchone()[0]} rows")
cursor.close()
conn.close()

# ============================================================
# 2. dynasties — TRUNCATE + INSERT
# ============================================================
print("\n2/6 upload dynasties (TRUNCATE)")
df = pd.read_csv(f"{BASE}/dynasties.csv")
rows = []
for _, r in df.iterrows():
    rows.append((
        int(r["id"]), r["name_zh"], r["name_en"],
        safe_int(r["start_year"]), safe_int(r["end_year"]),
        safe_str(r.get("description")), r["created_at"]
    ))
upload_rows("dynasties", rows,
    ["id", "name_zh", "name_en", "start_year", "end_year", "description", "created_at"])

# ============================================================
# 3. artists — TRUNCATE + INSERT
# ============================================================
print("\n3/6 upload artists (TRUNCATE)")
df = pd.read_csv(f"{BASE}/artists.csv")
rows = []
for _, r in df.iterrows():
    rows.append((
        int(r["id"]),
        safe_str(r.get("name_zh")), safe_str(r.get("name_en")),
        safe_int(r.get("birth_year")), safe_int(r.get("death_year")),
        safe_int(r.get("dynasty_id")),
        safe_str(r.get("biography")), safe_str(r.get("baidu_url")), safe_str(r.get("wiki_url")),
        r["created_at"], r["updated_at"]
    ))
upload_rows("artists", rows,
    ["id", "name_zh", "name_en", "birth_year", "death_year", "dynasty_id", "biography", "baidu_url", "wiki_url", "created_at", "updated_at"])

# ============================================================
# 4. artifacts — INSERT (daduhui data, object_id starts from 2501)
# ============================================================
print("\n4/6 upload artifacts (INSERT daduhui)")
df = pd.read_csv(f"{BASE}/daduhui_final.csv")
rows = []
for _, r in df.iterrows():
    rows.append((
        safe_str(r.get("object_id")),
        safe_str(r.get("title_zh")),
        safe_str(r.get("title_en")),
        safe_str(r.get("time_period")),
        safe_int(r.get("dynasty_id")),
        safe_str(r.get("type")),
        safe_str(r.get("material")),
        safe_str(r.get("description")),
        safe_str(r.get("dimensions")),
        safe_int(r.get("museum_id")),
        safe_int(r.get("location_id")),
        safe_str(r.get("detail_url")),
        safe_str(r.get("image_url")),
        safe_str(r.get("image_path")),
        safe_str(r.get("credit_line")),
        safe_str(r.get("accession_number")),
        safe_str(r.get("crawl_date")),
        safe_int(r.get("image_validated")),
        safe_str(r.get("last_updated")),
        safe_str(r.get("created_at"))
    ))
upload_rows("artifacts", rows,
    ["object_id", "title_zh", "title_en", "time_period", "dynasty_id", "type", "material", "description", "dimensions", "museum_id", "location_id", "detail_url", "image_url", "image_path", "credit_line", "accession_number", "crawl_date", "image_validated", "last_updated", "created_at"],
    truncate=False)

# ============================================================
# 5. artifact_images — INSERT
# ============================================================
print("\n5/6 upload artifact_images (INSERT)")
df = pd.read_csv(f"{BASE}/artifact_images.csv")
rows = []
for _, r in df.iterrows():
    rows.append((
        int(r["artifact_id"]),
        safe_str(r.get("image_url")),
        safe_str(r.get("image_path")),
        safe_int(r.get("is_primary")),
        safe_int(r.get("sort_order"))
    ))
upload_rows("artifact_images", rows,
    ["artifact_id", "image_url", "image_path", "is_primary", "sort_order"],
    truncate=False)

# ============================================================
# 6. artifact_artist — INSERT
# ============================================================
print("\n6/6 upload artifact_artist (INSERT)")
df = pd.read_csv(f"{BASE}/artifact_artist.csv")
rows = []
for _, r in df.iterrows():
    rows.append((
        int(r["artifact_id"]),
        int(r["artist_id"]),
        safe_str(r.get("relationship_type"))
    ))
upload_rows("artifact_artist", rows,
    ["artifact_id", "artist_id", "relationship_type"],
    truncate=False)

print("\nall done!")
