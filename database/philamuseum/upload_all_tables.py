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
        print(f"  ⏭️ {table_name}: 无数据，跳过")
        return

    conn = get_conn()
    cursor = conn.cursor()

    if truncate:
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            cursor.execute(f"TRUNCATE TABLE `{table_name}`")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            conn.commit()
            print(f"  ✅ 已清空 {table_name}")
        except Exception as e:
            try:
                cursor.execute(f"DELETE FROM `{table_name}`")
                conn.commit()
                print(f"  ✅ 已清空 {table_name} (DELETE)")
            except Exception as e2:
                print(f"  ⚠️ 清空失败: {e2}")

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
                        print(f"    ❌ 行{i} 失败: {e}")
                    break
        else:
            failed += 1

        if inserted % 50 == 0:
            try:
                conn.commit()
            except:
                conn = get_conn()
                cursor = conn.cursor()
            print(f"    进度: {inserted + failed}/{total}")

    try:
        conn.commit()
    except:
        pass

    try:
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        count = cursor.fetchone()[0]
        print(f"  ✅ {table_name}: {count} 条 (成功:{inserted}, 失败:{failed})")
    except:
        print(f"  ✅ {table_name}: 成功:{inserted}, 失败:{failed}")

    cursor.close()
    conn.close()

# ============================================================
# 1. museums — 不 TRUNCATE（可能已有其他博物馆），用 REPLACE
# ============================================================
print("=" * 50)
print("1/5 上传 museums (REPLACE, 保留 id=3)")
df = pd.read_csv("clean_museums.csv")
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
print(f"  ✅ museums: {cursor.fetchone()[0]} 条")
cursor.close()
conn.close()

# ============================================================
# 2. dynasties — TRUNCATE 后 INSERT 指定 id（保留外键引用）
# ============================================================
print("\n2/5 上传 dynasties (TRUNCATE + 指定 id)")
df = pd.read_csv("clean_dynasties.csv")
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
# 3. artists — TRUNCATE 后 INSERT 指定 id
# ============================================================
print("\n3/5 上传 artists (TRUNCATE + 指定 id)")
df = pd.read_csv("clean_artists.csv")
rows = []
for _, r in df.iterrows():
    rows.append((
        int(r["id"]),
        safe_str(r.get("name_zh")), r["name_en"],
        safe_int(r.get("birth_year")), safe_int(r.get("death_year")),
        safe_int(r.get("dynasty_id")),
        safe_str(r.get("biography")), safe_str(r.get("baidu_url")), safe_str(r.get("wiki_url")),
        r["created_at"], r["updated_at"]
    ))
upload_rows("artists", rows,
    ["id", "name_zh", "name_en", "birth_year", "death_year", "dynasty_id", "biography", "baidu_url", "wiki_url", "created_at", "updated_at"])

# ============================================================
# 4. artifact_images — TRUNCATE 后 INSERT
# ============================================================
print("\n4/5 上传 artifact_images (TRUNCATE)")
df = pd.read_csv("clean_artifact_images.csv")
rows = []
for _, r in df.iterrows():
    artifact_id = int(r["artifact_id"])
    image_url = str(r["image_url"])
    image_type = safe_str(r.get("image_type", "main"))
    is_primary = 1 if image_type == "main" else 0
    rows.append((artifact_id, image_url, None, is_primary, None))
upload_rows("artifact_images", rows,
    ["artifact_id", "image_url", "image_path", "is_primary", "sort_order"])

# ============================================================
# 5. artifact_artist — TRUNCATE 后 INSERT
# ============================================================
print("\n5/5 上传 artifact_artist (TRUNCATE)")
df = pd.read_csv("clean_artifact_artist.csv")
rows = []
for _, r in df.iterrows():
    rows.append((int(r["artifact_id"]), int(r["artist_id"]), str(r["relationship_type"])))
upload_rows("artifact_artist", rows,
    ["artifact_id", "artist_id", "relationship_type"])

print("\n🎉 全部上传完成！")
