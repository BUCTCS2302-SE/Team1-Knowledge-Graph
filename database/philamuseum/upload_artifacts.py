import pandas as pd
import pymysql
import numpy as np
import time

DB_HOST = ""
DB_PORT = 0
DB_USER = ""
DB_PASS = ""
DB_NAME = ""

CSV_FILE = "clean_artifacts_translated.csv"

VARCHAR_LIMITS = {
    "object_id": 100, "title_zh": 500, "title_en": 500,
    "time_period": 200, "type": 100, "material": 200,
    "dimensions": 200, "detail_url": 500, "image_url": 500,
    "image_path": 500, "credit_line": 300, "accession_number": 100,
}

df = pd.read_csv(CSV_FILE)

df["material"] = df["material_zh"].where(df["material_zh"].notna(), df["material"])
df["type"] = df["type_zh"].where(df["type_zh"].notna(), df["type"])
df["description"] = df["description_zh"].where(df["description_zh"].notna(), df["description"])

db_columns = [
    "object_id", "title_zh", "title_en", "time_period", "dynasty_id",
    "type", "material", "description", "dimensions", "museum_id",
    "location_id", "detail_url", "image_url", "image_path", "credit_line",
    "accession_number", "crawl_date", "image_validated", "last_updated", "created_at"
]

df_insert = df[db_columns].copy()

for col in df_insert.columns:
    df_insert[col] = df_insert[col].replace({np.nan: None})

for col, limit in VARCHAR_LIMITS.items():
    if col in df_insert.columns:
        df_insert[col] = df_insert[col].apply(
            lambda x: str(x)[:limit] if pd.notna(x) and len(str(x)) > limit else x
        )

def get_connection():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4", connect_timeout=30,
        read_timeout=60, write_timeout=60
    )

conn = get_connection()
cursor = conn.cursor()

cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
cursor.execute("TRUNCATE TABLE artifacts")
cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
conn.commit()
print(f"✅ 已清空 artifacts 表 (TRUNCATE)")

placeholders = ", ".join(["%s"] * len(db_columns))
columns_str = ", ".join([f"`{col}`" for col in db_columns])
insert_sql = f"INSERT INTO artifacts ({columns_str}) VALUES ({placeholders})"

total = len(df_insert)
inserted = 0
failed = 0
commit_batch = 50

for idx, row in df_insert.iterrows():
    values = tuple(row)
    retry = 0
    while retry < 3:
        try:
            cursor.execute(insert_sql, values)
            inserted += 1
            break
        except pymysql.MySQLError as e:
            err_str = str(e)
            if "2006" in err_str or "2013" in err_str or "Lost connection" in err_str or "2003" in err_str:
                retry += 1
                print(f"  🔄 连接断开，第{retry}次重连...")
                try:
                    cursor.close()
                    conn.close()
                except:
                    pass
                time.sleep(3)
                conn = get_connection()
                cursor = conn.cursor()
                continue
            else:
                failed += 1
                if failed <= 10:
                    print(f"  ❌ object_id={values[0]} 失败: {e}")
                break
    else:
        failed += 1
        print(f"  ❌ object_id={values[0]} 重试3次仍失败")

    if inserted % commit_batch == 0:
        try:
            conn.commit()
        except:
            conn = get_connection()
            cursor = conn.cursor()
        print(f"  进度: {inserted + failed}/{total} (成功:{inserted}, 失败:{failed})")

try:
    conn.commit()
except:
    pass
print(f"  最终进度: {inserted + failed}/{total} (成功:{inserted}, 失败:{failed})")

try:
    cursor.execute("SELECT COUNT(*) FROM artifacts")
    count = cursor.fetchone()[0]
    print(f"\n🎉 上传完成！artifacts 表当前共 {count} 条记录")
except:
    print(f"\n🎉 上传完成！本次成功:{inserted}, 失败:{failed}")

cursor.close()
conn.close()
