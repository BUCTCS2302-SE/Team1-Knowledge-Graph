import csv, re, time
import pymysql
import pandas as pd
import numpy as np
from datetime import date

today = date.today().isoformat()

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
    try:
        return int(val)
    except:
        return None

def safe_str(val):
    if pd.isna(val) or str(val).strip() == '' or str(val) == 'nan':
        return None
    return str(val).strip()

def upload_rows(table_name, rows, columns, truncate=False):
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
            print(f"  truncate failed: {e}")

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
                if any(code in err_str for code in ["2006", "2013", "Lost connection", "2003"]):
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


# ===== 读取数据 =====
BASE = r'e:\软工\Asian Art Museum of San Francisco'
csv_path = f"{BASE}\\asian_final_translated.csv"
df = pd.read_csv(csv_path, encoding='utf-8-sig')
print(f"CSV行数: {len(df)}")
print(f"CSV列名: {list(df.columns)}")

# 读取原始CSV获取Artist信息
orig_path = f"{BASE}\\objects_china_verified.csv"
orig_df = pd.read_csv(orig_path, encoding='gbk')
obj_artist_map = {}
for _, r in orig_df.iterrows():
    acc = str(r['Object number']).strip()
    artist = str(r['Artist']).strip() if pd.notna(r['Artist']) else ''
    obj_artist_map[acc] = artist

# ===== 1. museums - REPLACE id=2 =====
print("\n1/5 upload museums (REPLACE id=2)")
conn = get_conn()
cursor = conn.cursor()
cursor.execute(
    "REPLACE INTO museums (id, name, short_name, country, city, website, collection_url, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    (2, 'Asian Art Museum of San Francisco', 'Asian Art Museum', 'United States', 'San Francisco',
     'https://asianart.org', 'https://searchcollection.asianart.org', today, today)
)
conn.commit()
cursor.execute("SELECT COUNT(*) FROM museums")
print(f"  done museums: {cursor.fetchone()[0]} rows")
cursor.close()
conn.close()

# ===== 2. artists - 追加新艺术家 =====
print("\n2/5 upload artists (APPEND)")

# 从CSV中提取艺术家
artist_set = {}
for _, r in df.iterrows():
    acc = str(r['accession_number']).strip()
    artist = obj_artist_map.get(acc, '')
    if not artist:
        continue
    key = artist.lower().strip()
    if key not in artist_set:
        artist_set[key] = {
            'name_en': artist,
            'name_zh': '',  # 后续可翻译
        }

# 查询当前最大artist id
conn = get_conn()
cursor = conn.cursor()
cursor.execute("SELECT MAX(id) FROM artists")
max_id = cursor.fetchone()[0]
cursor.close()
conn.close()
next_id = (max_id or 0) + 1
print(f"  当前artists max id: {max_id}, 新艺术家从 {next_id} 开始")

# 分配id
artist_rows = []
artist_name_to_id = {}
for key, info in sorted(artist_set.items()):
    aid = next_id
    next_id += 1
    artist_name_to_id[key] = aid
    artist_rows.append((
        aid,
        safe_str(info['name_zh']),
        safe_str(info['name_en']),
        None, None, None, None, None, None,
        today, today
    ))

upload_rows('artists', artist_rows,
    ['id', 'name_zh', 'name_en', 'birth_year', 'death_year', 'dynasty_id',
     'biography', 'baidu_url', 'wiki_url', 'created_at', 'updated_at'],
    truncate=False)

# ===== 3. artifacts - INSERT =====
print("\n3/5 upload artifacts (INSERT)")
artifact_rows = []
for _, r in df.iterrows():
    artifact_rows.append((
        safe_str(r['object_id']),
        safe_str(r.get('title_zh')),
        safe_str(r.get('title_en')),
        safe_str(r.get('time_period')),
        safe_int(r.get('dynasty_id')),
        safe_str(r.get('type')),
        safe_str(r.get('material')),
        safe_str(r.get('description')),
        safe_str(r.get('dimensions')),
        safe_int(r.get('museum_id')),
        safe_int(r.get('location_id')),
        safe_str(r.get('detail_url')),
        safe_str(r.get('image_url')),
        safe_str(r.get('image_path')),
        safe_str(r.get('credit_line')),
        safe_str(r.get('accession_number')),
        safe_str(r.get('crawl_date')),
        safe_int(r.get('image_validated')),
        safe_str(r.get('last_updated')),
        safe_str(r.get('created_at'))
    ))

upload_rows('artifacts', artifact_rows,
    ['object_id', 'title_zh', 'title_en', 'time_period', 'dynasty_id', 'type',
     'material', 'description', 'dimensions', 'museum_id', 'location_id',
     'detail_url', 'image_url', 'image_path', 'credit_line', 'accession_number',
     'crawl_date', 'image_validated', 'last_updated', 'created_at'],
    truncate=False)

# ===== 4. artifact_images - INSERT =====
print("\n4/5 upload artifact_images (INSERT)")

# 查询当前最大image id
conn = get_conn()
cursor = conn.cursor()
cursor.execute("SELECT MAX(id) FROM artifact_images")
max_img_id = cursor.fetchone()[0]
cursor.close()
conn.close()
next_img_id = (max_img_id or 0) + 1
print(f"  当前artifact_images max id: {max_img_id}, 新记录从 {next_img_id} 开始")

img_rows = []
for _, r in df.iterrows():
    img_rows.append((
        next_img_id,
        int(r['object_id']),
        safe_str(r.get('image_url')),
        safe_str(r.get('image_path')),
        1, 1
    ))
    next_img_id += 1

upload_rows('artifact_images', img_rows,
    ['id', 'artifact_id', 'image_url', 'image_path', 'is_primary', 'sort_order'],
    truncate=False)

# ===== 5. artifact_artist - INSERT =====
print("\n5/5 upload artifact_artist (INSERT)")
aa_rows = []
for _, r in df.iterrows():
    acc = str(r['accession_number']).strip()
    artist = obj_artist_map.get(acc, '')
    if not artist:
        continue
    key = artist.lower().strip()
    aid = artist_name_to_id.get(key)
    if aid:
        aa_rows.append((
            int(r['object_id']),
            aid,
            'creator'
        ))

upload_rows('artifact_artist', aa_rows,
    ['artifact_id', 'artist_id', 'relationship_type'],
    truncate=False)

print("\n===== 全部上传完成 =====")
