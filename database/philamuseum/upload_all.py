"""
费城艺术博物馆 - 数据库全量上传脚本
功能：将清洗翻译后的数据一次性上传至 MySQL 数据库
执行顺序：
  1. museums (REPLACE) — 博物馆信息
  2. dynasties (TRUNCATE) — 朝代信息
  3. artists (TRUNCATE) — 艺术家信息
  4. artifacts (TRUNCATE) — 文物主表（含中文翻译字段优先、VARCHAR截断保护）
  5. artifact_images (TRUNCATE) — 文物图片
  6. artifact_artist (TRUNCATE) — 文物-艺术家关联
  7. 描述字段补充 — 用材质填充空描述
"""

import pandas as pd
import pymysql
import numpy as np
import time

# ============================================================
# 数据库配置
# ============================================================
DB_HOST = ""
DB_PORT = 0
DB_USER = ""
DB_PASS = ""
DB_NAME = ""

# artifacts 表 VARCHAR 字段长度限制
VARCHAR_LIMITS = {
    "object_id": 100, "title_zh": 500, "title_en": 500,
    "time_period": 200, "type": 100, "material": 200,
    "dimensions": 200, "detail_url": 500, "image_url": 500,
    "image_path": 500, "credit_line": 300, "accession_number": 100,
}

# CSV 文件路径
CSV_MUSEUMS = "clean_museums.csv"
CSV_DYNASTIES = "clean_dynasties.csv"
CSV_ARTISTS = "clean_artists.csv"
CSV_ARTIFACTS = "clean_artifacts_translated.csv"
CSV_ARTIFACT_IMAGES = "clean_artifact_images.csv"
CSV_ARTIFACT_ARTIST = "clean_artifact_artist.csv"


# ============================================================
# 通用工具函数
# ============================================================
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


def truncate_table(conn, cursor, table_name):
    """清空指定表"""
    try:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute(f"TRUNCATE TABLE `{table_name}`")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        print(f"  ✅ 已清空 {table_name}")
    except Exception:
        try:
            cursor.execute(f"DELETE FROM `{table_name}`")
            conn.commit()
            print(f"  ✅ 已清空 {table_name} (DELETE)")
        except Exception as e2:
            print(f"  ⚠️ 清空失败: {e2}")


def upload_rows(table_name, rows, columns, truncate=True):
    """通用批量上传函数，支持断线重连"""
    if not rows:
        print(f"  ⏭️ {table_name}: 无数据，跳过")
        return

    conn = get_conn()
    cursor = conn.cursor()

    if truncate:
        truncate_table(conn, cursor, table_name)

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
                    except Exception:
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
            except Exception:
                conn = get_conn()
                cursor = conn.cursor()
            print(f"    进度: {inserted + failed}/{total}")

    try:
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        count = cursor.fetchone()[0]
        print(f"  ✅ {table_name}: {count} 条 (成功:{inserted}, 失败:{failed})")
    except Exception:
        print(f"  ✅ {table_name}: 成功:{inserted}, 失败:{failed}")

    cursor.close()
    conn.close()


def batch_update(table_name, update_data, desc_col="description"):
    """通用批量更新函数，用于补充描述字段"""
    if not update_data:
        print(f"  ⏭️ {table_name}: 无需更新")
        return

    print(f"  待更新: {len(update_data)} 条")
    updated = 0
    failed = 0

    for _, row in update_data.iterrows():
        obj_id = str(row["object_id"])
        desc = str(row[desc_col])
        if desc == 'nan' or not desc.strip():
            continue

        for attempt in range(3):
            try:
                conn = get_conn()
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE `{table_name}` SET {desc_col} = %s WHERE object_id = %s",
                    (desc, obj_id)
                )
                conn.commit()
                cursor.close()
                conn.close()
                updated += 1
                break
            except Exception as e:
                try:
                    cursor.close()
                    conn.close()
                except Exception:
                    pass
                if attempt == 2:
                    failed += 1
                    if failed <= 5:
                        print(f"  ❌ object_id={obj_id} 失败: {e}")
                else:
                    time.sleep(2)

        if updated % 200 == 0 and updated > 0:
            print(f"  进度: {updated + failed}/{len(update_data)}")

    print(f"  ✅ 描述补充完成！成功:{updated}, 失败:{failed}")


# ============================================================
# 步骤 1: 上传 museums (REPLACE)
# ============================================================
def upload_museums():
    print("=" * 60)
    print("1/6 上传 museums (REPLACE)")
    df = pd.read_csv(CSV_MUSEUMS)
    conn = get_conn()
    cursor = conn.cursor()
    for _, r in df.iterrows():
        cursor.execute(
            "REPLACE INTO museums (id, name, short_name, country, city, website, collection_url, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (int(r["id"]), r["name"], r["short_name"], r["country"], r["city"],
             r["website"], r["collection_url"], r["created_at"], r["updated_at"])
        )
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM museums")
    print(f"  ✅ museums: {cursor.fetchone()[0]} 条")
    cursor.close()
    conn.close()


# ============================================================
# 步骤 2: 上传 dynasties (TRUNCATE)
# ============================================================
def upload_dynasties():
    print("\n2/6 上传 dynasties (TRUNCATE + 指定 id)")
    df = pd.read_csv(CSV_DYNASTIES)
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
# 步骤 3: 上传 artists (TRUNCATE)
# ============================================================
def upload_artists():
    print("\n3/6 上传 artists (TRUNCATE + 指定 id)")
    df = pd.read_csv(CSV_ARTISTS)
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
                ["id", "name_zh", "name_en", "birth_year", "death_year", "dynasty_id",
                 "biography", "baidu_url", "wiki_url", "created_at", "updated_at"])


# ============================================================
# 步骤 4: 上传 artifacts (TRUNCATE, 翻译字段优先 + VARCHAR截断)
# ============================================================
def upload_artifacts():
    print("\n4/6 上传 artifacts (TRUNCATE, 中文翻译优先, VARCHAR截断保护)")
    df = pd.read_csv(CSV_ARTIFACTS)

    # 中文翻译字段优先替换英文字段
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

    # NaN -> None
    for col in df_insert.columns:
        df_insert[col] = df_insert[col].replace({np.nan: None})

    # VARCHAR 长度截断保护
    for col, limit in VARCHAR_LIMITS.items():
        if col in df_insert.columns:
            df_insert[col] = df_insert[col].apply(
                lambda x: str(x)[:limit] if pd.notna(x) and len(str(x)) > limit else x
            )

    # 清空表
    conn = get_conn()
    cursor = conn.cursor()
    truncate_table(conn, cursor, "artifacts")

    # 批量插入
    placeholders = ", ".join(["%s"] * len(db_columns))
    columns_str = ", ".join([f"`{col}`" for col in db_columns])
    insert_sql = f"INSERT INTO artifacts ({columns_str}) VALUES ({placeholders})"

    total = len(df_insert)
    inserted = 0
    failed = 0

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
                if any(code in err_str for code in ["2006", "2013", "Lost connection", "2003"]):
                    retry += 1
                    print(f"  🔄 连接断开，第{retry}次重连...")
                    try:
                        cursor.close()
                        conn.close()
                    except Exception:
                        pass
                    time.sleep(3)
                    conn = get_conn()
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

        if inserted % 50 == 0:
            try:
                conn.commit()
            except Exception:
                conn = get_conn()
                cursor = conn.cursor()
            print(f"  进度: {inserted + failed}/{total} (成功:{inserted}, 失败:{failed})")

    try:
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("SELECT COUNT(*) FROM artifacts")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM artifacts WHERE description IS NOT NULL AND description != ''")
        desc_count = cursor.fetchone()[0]
        print(f"  ✅ artifacts: {count} 条 (成功:{inserted}, 失败:{failed}), 有描述:{desc_count}")
    except Exception:
        print(f"  ✅ artifacts: 成功:{inserted}, 失败:{failed}")

    cursor.close()
    conn.close()


# ============================================================
# 步骤 5: 上传 artifact_images (TRUNCATE)
# ============================================================
def upload_artifact_images():
    print("\n5/6 上传 artifact_images (TRUNCATE)")
    df = pd.read_csv(CSV_ARTIFACT_IMAGES)
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
# 步骤 6: 上传 artifact_artist (TRUNCATE)
# ============================================================
def upload_artifact_artist():
    print("\n6/6 上传 artifact_artist (TRUNCATE)")
    df = pd.read_csv(CSV_ARTIFACT_ARTIST)
    rows = []
    for _, r in df.iterrows():
        rows.append((int(r["artifact_id"]), int(r["artist_id"]), str(r["relationship_type"])))
    upload_rows("artifact_artist", rows,
                ["artifact_id", "artist_id", "relationship_type"])


# ============================================================
# 步骤 7: 描述字段补充（用材质填充空描述）
# ============================================================
def fill_missing_descriptions():
    print("\n" + "=" * 60)
    print("7/7 补充空描述字段（用材质填充）")
    df = pd.read_csv(CSV_ARTIFACTS)

    # 用中文翻译优先
    df["description"] = df["description_zh"].where(df["description_zh"].notna(), df["description"])

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT object_id FROM artifacts WHERE description IS NULL OR description = ''")
    empty_ids = set(str(r[0]) for r in cursor.fetchall())
    cursor.close()
    conn.close()

    print(f"  数据库无描述: {len(empty_ids)} 条")

    # 对无描述的记录，用 material 填充
    no_desc = df['object_id'].astype(str).isin(empty_ids)
    has_material = df['material'].notna() & (df['material'].astype(str).str.strip() != '') & (df['material'].astype(str) != 'nan')
    fill_mask = no_desc & has_material

    df.loc[fill_mask, 'description'] = df.loc[fill_mask, 'material']

    update_rows = df[fill_mask][['object_id', 'description']].copy()
    batch_update("artifacts", update_rows, "description")


# ============================================================
# 主流程
# ============================================================
if __name__ == "__main__":
    print("🚀 开始上传费城艺术博物馆数据至 MySQL")
    print(f"   数据库: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print()

    upload_museums()
    upload_dynasties()
    upload_artists()
    upload_artifacts()
    upload_artifact_images()
    upload_artifact_artist()
    fill_missing_descriptions()

    print("\n" + "=" * 60)
    print("🎉 全部上传完成！")
