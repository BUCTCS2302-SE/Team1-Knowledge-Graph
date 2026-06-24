import pandas as pd
import pymysql
import re
import time

DB_HOST = ""
DB_PORT = 0
DB_USER = ""
DB_PASS = ""
DB_NAME = ""

df = pd.read_csv('clean_artifacts_translated.csv')
df["description"] = df["description_zh"].where(df["description_zh"].notna(), df["description"])
update_data = df[df["description"].notna()][["object_id", "description"]].copy()

print(f"待更新: {len(update_data)} 条")

def get_conn():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, charset="utf8mb4", connect_timeout=30,
        read_timeout=60, write_timeout=60
    )

updated = 0
failed = 0

for _, row in update_data.iterrows():
    obj_id = str(row["object_id"])
    desc = str(row["description"])
    if desc == 'nan' or not desc.strip():
        continue

    for attempt in range(3):
        try:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute("UPDATE artifacts SET description = %s WHERE object_id = %s", (desc, obj_id))
            conn.commit()
            cursor.close()
            conn.close()
            updated += 1
            break
        except Exception as e:
            try:
                cursor.close()
                conn.close()
            except:
                pass
            if attempt == 2:
                failed += 1
                if failed <= 5:
                    print(f"  ❌ object_id={obj_id} 失败: {e}")
            else:
                time.sleep(2)

    if updated % 50 == 0 and updated > 0:
        print(f"  进度: {updated + failed}/{len(update_data)} (成功:{updated}, 失败:{failed})")

print(f"\n✅ 完成！成功:{updated}, 失败:{failed}")
