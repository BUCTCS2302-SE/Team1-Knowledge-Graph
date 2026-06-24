import pandas as pd
import numpy as np
import os
from datetime import date

DATA_DIR = r"e:\软工\philamuseum"
TARGET_COUNT = 2500
TODAY = str(date.today())

df_artifacts = pd.read_csv(os.path.join(DATA_DIR, "clean_artifacts.csv"))
print(f"当前 clean_artifacts.csv: {len(df_artifacts)} 条")

df_translated = pd.read_csv(os.path.join(DATA_DIR, "clean_artifacts_translated.csv"))
print(f"当前 clean_artifacts_translated.csv: {len(df_translated)} 条")

if len(df_artifacts) != TARGET_COUNT:
    print(f"⚠️ 当前 {len(df_artifacts)} 条, 需要 {TARGET_COUNT} 条, 需要重新筛选")
    has_title_zh = df_translated['title_zh'].notna() & (df_translated['title_zh'].astype(str).str.strip() != '')
    has_material_zh = ~df_translated['material'].notna() | (df_translated['material_zh'].notna() & (df_translated['material_zh'].astype(str).str.strip() != ''))
    has_type_zh = df_translated['type_zh'].notna() & (df_translated['type_zh'].astype(str).str.strip() != '')
    has_desc_zh = ~df_translated['description'].notna() | (df_translated['description_zh'].notna() & (df_translated['description_zh'].astype(str).str.strip() != ''))
    has_image = df_translated['image_url'].notna() & (df_translated['image_url'].astype(str).str.strip() != '')
    has_dynasty = df_translated['dynasty_id'].notna()

    fully_translated = has_title_zh & has_material_zh & has_type_zh & has_desc_zh & has_image & has_dynasty
    df_clean = df_translated[fully_translated].copy()
    print(f"完全翻译+有图+有朝代: {len(df_clean)} 条")

    np.random.seed(42)
    dynasty_counts = df_clean['dynasty_id'].value_counts()
    sample_indices = []

    for dynasty_id, count in dynasty_counts.items():
        dynasty_df = df_clean[df_clean['dynasty_id'] == dynasty_id]
        proportion = count / len(df_clean)
        n_samples = max(1, round(proportion * TARGET_COUNT))
        if n_samples >= len(dynasty_df):
            sample_indices.extend(dynasty_df.index.tolist())
        else:
            sampled = dynasty_df.sample(n=n_samples, random_state=42)
            sample_indices.extend(sampled.index.tolist())

    df_selected = df_clean.loc[sample_indices].copy()
    if len(df_selected) > TARGET_COUNT:
        df_selected = df_selected.head(TARGET_COUNT)
    elif len(df_selected) < TARGET_COUNT:
        remaining = df_clean[~df_clean.index.isin(df_selected.index)]
        need = TARGET_COUNT - len(df_selected)
        extra = remaining.sample(n=need, random_state=42)
        df_selected = pd.concat([df_selected, extra])

    df_selected = df_selected.sort_values('object_id').reset_index(drop=True)
    df_selected['object_id'] = range(1, len(df_selected) + 1)
    print(f"最终选取: {len(df_selected)} 条")

    df_artifacts_only = df_selected.drop(columns=['title_zh', 'material_zh', 'type_zh', 'description_zh'], errors='ignore')
    df_artifacts_only.to_csv(os.path.join(DATA_DIR, "clean_artifacts.csv"), index=False, encoding='utf-8-sig')
    df_selected.to_csv(os.path.join(DATA_DIR, "clean_artifacts_translated.csv"), index=False, encoding='utf-8-sig')
    print(f"✅ clean_artifacts.csv ({len(df_artifacts_only)} 条)")
    print(f"✅ clean_artifacts_translated.csv ({len(df_selected)} 条)")
else:
    print(f"✅ 已是 {TARGET_COUNT} 条, 无需重新筛选")

df_artifacts = pd.read_csv(os.path.join(DATA_DIR, "clean_artifacts.csv"))
acc_set = set(df_artifacts['accession_number'].dropna().astype(int))
obj_id_map = dict(zip(df_artifacts['accession_number'], df_artifacts['object_id']))
print(f"\naccession_number -> object_id 映射: {len(obj_id_map)} 条")

print("\n=== 重新生成 artifact_images ===")
images_rows = []
for _, row in df_artifacts.iterrows():
    if pd.notna(row.get('image_url')) and str(row.get('image_url', '')).strip():
        images_rows.append({
            'artifact_id': int(row['object_id']),
            'image_url': row['image_url'],
            'image_type': 'main',
            'created_at': TODAY,
        })
df_images = pd.DataFrame(images_rows)
df_images.insert(0, 'id', range(1, len(df_images) + 1))
df_images.to_csv(os.path.join(DATA_DIR, "clean_artifact_images.csv"), index=False, encoding='utf-8-sig')
print(f"✅ clean_artifact_images.csv ({len(df_images)} 条)")

print("\n=== 重新生成 artists 和 artifact_artist ===")
df_orig = pd.read_csv(os.path.join(DATA_DIR, "Philamuseum_chinese_made_artworks_final.csv"))
df_orig_matched = df_orig[df_orig['藏品编号'].isin(acc_set)].copy()

artist_name_to_id = {}
artist_rows = []
aa_rows = []
artist_counter = 1

for _, row in df_orig_matched.iterrows():
    acc_num = int(row['藏品编号'])
    if acc_num not in obj_id_map:
        continue
    artifact_id = int(obj_id_map[acc_num])

    artist_name = str(row.get('作者', '')).strip()
    if not artist_name or artist_name.lower() in ('nan', 'unknown', 'artist/maker unknown'):
        continue

    if artist_name not in artist_name_to_id:
        artist_name_to_id[artist_name] = artist_counter
        artist_rows.append({
            'id': artist_counter,
            'name_zh': None,
            'name_en': artist_name,
            'birth_year': None,
            'death_year': None,
            'dynasty_id': None,
            'biography': None,
            'baidu_url': None,
            'wiki_url': None,
            'created_at': TODAY,
            'updated_at': TODAY,
        })
        artist_counter += 1

    aa_rows.append({
        'artifact_id': artifact_id,
        'artist_id': artist_name_to_id[artist_name],
        'relationship_type': 'creator',
    })

df_artists = pd.DataFrame(artist_rows)
df_artists.to_csv(os.path.join(DATA_DIR, "clean_artists.csv"), index=False, encoding='utf-8-sig')
print(f"✅ clean_artists.csv ({len(df_artists)} 条)")

df_aa = pd.DataFrame(aa_rows)
df_aa.to_csv(os.path.join(DATA_DIR, "clean_artifact_artist.csv"), index=False, encoding='utf-8-sig')
print(f"✅ clean_artifact_artist.csv ({len(df_aa)} 条)")

print("\n=== 重新生成 artists_translated ===")
df_artists_t = df_artists.copy()
df_artists_t.to_csv(os.path.join(DATA_DIR, "clean_artists_translated.csv"), index=False, encoding='utf-8-sig')
print(f"✅ clean_artists_translated.csv ({len(df_artists_t)} 条) [name_zh 待翻译]")

print("\n=== 重新生成 dynasties ===")
used_dynasty_ids = set(df_artifacts['dynasty_id'].dropna().astype(int))
all_dynasties = [
    {"id": 1, "name_zh": "商朝", "name_en": "Shang Dynasty", "start_year": -1600, "end_year": -1050},
    {"id": 2, "name_zh": "周朝", "name_en": "Zhou Dynasty", "start_year": -1100, "end_year": -256},
    {"id": 3, "name_zh": "西周", "name_en": "Western Zhou Dynasty", "start_year": -1100, "end_year": -771},
    {"id": 4, "name_zh": "东周", "name_en": "Eastern Zhou Dynasty", "start_year": -770, "end_year": -256},
    {"id": 5, "name_zh": "战国", "name_en": "Warring States Period", "start_year": -476, "end_year": -221},
    {"id": 6, "name_zh": "秦朝", "name_en": "Qin Dynasty", "start_year": -221, "end_year": -206},
    {"id": 7, "name_zh": "汉朝", "name_en": "Han Dynasty", "start_year": -206, "end_year": 220},
    {"id": 8, "name_zh": "西汉", "name_en": "Western Han Dynasty", "start_year": -206, "end_year": 9},
    {"id": 9, "name_zh": "东汉", "name_en": "Eastern Han Dynasty", "start_year": 25, "end_year": 220},
    {"id": 10, "name_zh": "六朝", "name_en": "Six Dynasties Period", "start_year": 220, "end_year": 589},
    {"id": 11, "name_zh": "西晋", "name_en": "Western Jin Dynasty", "start_year": 265, "end_year": 317},
    {"id": 12, "name_zh": "南北朝", "name_en": "Northern and Southern Dynasties", "start_year": 317, "end_year": 589},
    {"id": 13, "name_zh": "北朝", "name_en": "Northern Dynasties", "start_year": 386, "end_year": 581},
    {"id": 14, "name_zh": "南朝", "name_en": "Southern Dynasties", "start_year": 317, "end_year": 589},
    {"id": 15, "name_zh": "北魏", "name_en": "Northern Wei Dynasty", "start_year": 386, "end_year": 535},
    {"id": 16, "name_zh": "北齐", "name_en": "Northern Qi Dynasty", "start_year": 550, "end_year": 577},
    {"id": 17, "name_zh": "隋朝", "name_en": "Sui Dynasty", "start_year": 581, "end_year": 618},
    {"id": 18, "name_zh": "唐朝", "name_en": "Tang Dynasty", "start_year": 618, "end_year": 907},
    {"id": 19, "name_zh": "五代", "name_en": "Five Dynasties", "start_year": 907, "end_year": 960},
    {"id": 20, "name_zh": "辽朝", "name_en": "Liao Dynasty", "start_year": 907, "end_year": 1125},
    {"id": 21, "name_zh": "宋朝", "name_en": "Song Dynasty", "start_year": 960, "end_year": 1279},
    {"id": 22, "name_zh": "北宋", "name_en": "Northern Song Dynasty", "start_year": 960, "end_year": 1127},
    {"id": 23, "name_zh": "南宋", "name_en": "Southern Song Dynasty", "start_year": 1127, "end_year": 1279},
    {"id": 24, "name_zh": "金朝", "name_en": "Jin Dynasty", "start_year": 1115, "end_year": 1234},
    {"id": 25, "name_zh": "元朝", "name_en": "Yuan Dynasty", "start_year": 1271, "end_year": 1368},
    {"id": 26, "name_zh": "明朝", "name_en": "Ming Dynasty", "start_year": 1368, "end_year": 1644},
    {"id": 27, "name_zh": "清朝", "name_en": "Qing Dynasty", "start_year": 1644, "end_year": 1911},
    {"id": 28, "name_zh": "中华民国", "name_en": "Republican Period", "start_year": 1912, "end_year": 1949},
]
df_dynasties = pd.DataFrame(all_dynasties)
df_dynasties = df_dynasties[df_dynasties['id'].isin(used_dynasty_ids)]
df_dynasties['description'] = None
df_dynasties['created_at'] = TODAY
df_dynasties.to_csv(os.path.join(DATA_DIR, "clean_dynasties.csv"), index=False, encoding='utf-8-sig')
print(f"✅ clean_dynasties.csv ({len(df_dynasties)} 条)")

print("\n=== 确认 museums ===")
df_museums = pd.DataFrame([{
    'id': 1,
    'name': 'Philadelphia Museum of Art',
    'short_name': 'Philamuseum',
    'country': 'United States',
    'city': 'Philadelphia',
    'website': 'https://www.philamuseum.org',
    'collection_url': 'https://www.philamuseum.org/collection',
    'created_at': TODAY,
    'updated_at': TODAY,
}])
df_museums.to_csv(os.path.join(DATA_DIR, "clean_museums.csv"), index=False, encoding='utf-8-sig')
print(f"✅ clean_museums.csv ({len(df_museums)} 条)")

print("\n=== 确认原始CSV ===")
df_original = pd.read_csv(os.path.join(DATA_DIR, "Philamuseum_chinese_made_artworks_final.csv"))
df_original_filtered = df_original[df_original['藏品编号'].isin(acc_set)].copy()
df_original_filtered.to_csv(os.path.join(DATA_DIR, "Philamuseum_chinese_made_artworks_final.csv"), index=False, encoding='utf-8-sig')
print(f"✅ Philamuseum_chinese_made_artworks_final.csv ({len(df_original_filtered)} 条)")

print("\n🎉 所有文件已重新生成！")
