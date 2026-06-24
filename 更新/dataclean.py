import pandas as pd
import re
from datetime import date

RAW_PATH = "Philamuseum_chinese_made_artworks_final.csv"
OUTPUT_DIR = "."

df = pd.read_csv(RAW_PATH)
df = df.drop_duplicates()

MUSEUM_ID = 1
CRAWL_DATE = str(date.today())

CANONICAL_DYNASTIES = [
    {"name_en": "Shang Dynasty", "name_zh": "商朝", "start_year": -1600, "end_year": -1050},
    {"name_en": "Zhou Dynasty", "name_zh": "周朝", "start_year": -1100, "end_year": -256},
    {"name_en": "Western Zhou Dynasty", "name_zh": "西周", "start_year": -1100, "end_year": -771},
    {"name_en": "Eastern Zhou Dynasty", "name_zh": "东周", "start_year": -770, "end_year": -256},
    {"name_en": "Warring States Period", "name_zh": "战国", "start_year": -476, "end_year": -221},
    {"name_en": "Qin Dynasty", "name_zh": "秦朝", "start_year": -221, "end_year": -206},
    {"name_en": "Han Dynasty", "name_zh": "汉朝", "start_year": -206, "end_year": 220},
    {"name_en": "Western Han Dynasty", "name_zh": "西汉", "start_year": -206, "end_year": 9},
    {"name_en": "Eastern Han Dynasty", "name_zh": "东汉", "start_year": 25, "end_year": 220},
    {"name_en": "Six Dynasties Period", "name_zh": "六朝", "start_year": 220, "end_year": 589},
    {"name_en": "Western Jin Dynasty", "name_zh": "西晋", "start_year": 265, "end_year": 317},
    {"name_en": "Northern and Southern Dynasties", "name_zh": "南北朝", "start_year": 317, "end_year": 589},
    {"name_en": "Northern Dynasties", "name_zh": "北朝", "start_year": 386, "end_year": 581},
    {"name_en": "Southern Dynasties", "name_zh": "南朝", "start_year": 317, "end_year": 589},
    {"name_en": "Northern Wei Dynasty", "name_zh": "北魏", "start_year": 386, "end_year": 535},
    {"name_en": "Northern Qi Dynasty", "name_zh": "北齐", "start_year": 550, "end_year": 577},
    {"name_en": "Sui Dynasty", "name_zh": "隋朝", "start_year": 581, "end_year": 618},
    {"name_en": "Tang Dynasty", "name_zh": "唐朝", "start_year": 618, "end_year": 907},
    {"name_en": "Five Dynasties", "name_zh": "五代", "start_year": 907, "end_year": 960},
    {"name_en": "Liao Dynasty", "name_zh": "辽朝", "start_year": 907, "end_year": 1125},
    {"name_en": "Song Dynasty", "name_zh": "宋朝", "start_year": 960, "end_year": 1279},
    {"name_en": "Northern Song Dynasty", "name_zh": "北宋", "start_year": 960, "end_year": 1127},
    {"name_en": "Southern Song Dynasty", "name_zh": "南宋", "start_year": 1127, "end_year": 1279},
    {"name_en": "Jin Dynasty", "name_zh": "金朝", "start_year": 1115, "end_year": 1234},
    {"name_en": "Yuan Dynasty", "name_zh": "元朝", "start_year": 1271, "end_year": 1368},
    {"name_en": "Ming Dynasty", "name_zh": "明朝", "start_year": 1368, "end_year": 1644},
    {"name_en": "Qing Dynasty", "name_zh": "清朝", "start_year": 1644, "end_year": 1911},
    {"name_en": "Republican Period", "name_zh": "中华民国", "start_year": 1912, "end_year": 1949},
]

MATCH_KEYWORDS = [
    ("Qing Dynasty", "Qing"),
    ("Ming Dynasty", "Ming"),
    ("Yuan Dynasty", "Yuan"),
    ("Jin Dynasty", "Jin"),
    ("Northern Song Dynasty", "Northern Song"),
    ("Southern Song Dynasty", "Southern Song"),
    ("Song Dynasty", "Song"),
    ("Tang Dynasty", "Tang"),
    ("Sui Dynasty", "Sui"),
    ("Western Han Dynasty", "Western Han"),
    ("Eastern Han Dynasty", "Eastern Han"),
    ("Han Dynasty", "Han"),
    ("Liao Dynasty", "Liao"),
    ("Western Zhou Dynasty", "Western Zhou"),
    ("Eastern Zhou Dynasty", "Eastern Zhou"),
    ("Zhou Dynasty", "Zhou"),
    ("Shang Dynasty", "Shang"),
    ("Northern Wei Dynasty", "Northern Wei"),
    ("Northern Qi Dynasty", "Northern Qi"),
    ("Qin Dynasty", "Qin"),
    ("Warring States Period", "Warring States"),
    ("Republican Period", "Republican"),
    ("Five Dynasties", "Five Dynasties"),
    ("Six Dynasties Period", "Six Dynasties"),
    ("Northern and Southern Dynasties", "Northern and Southern"),
    ("Northern Dynasties", "Northern Dynasties"),
    ("Southern Dynasties", "Southern Dynasties"),
    ("Western Jin Dynasty", "Western Jin"),
]


def match_dynasty(raw):
    if pd.isna(raw) or not str(raw).strip():
        return None
    raw_lower = str(raw).strip().lower()
    raw_lower = raw_lower.replace('northen', 'northern')
    for canonical_name, keyword in MATCH_KEYWORDS:
        if keyword.lower() in raw_lower:
            return canonical_name
    return None


museum_row = pd.DataFrame([{
    'id': MUSEUM_ID,
    'name': 'Philadelphia Museum of Art',
    'short_name': 'Philamuseum',
    'country': 'United States',
    'city': 'Philadelphia',
    'website': 'https://www.philamuseum.org',
    'collection_url': 'https://www.philamuseum.org/collection',
    'created_at': CRAWL_DATE,
    'updated_at': CRAWL_DATE,
}])

dynasty_id_map = {}
dynasty_rows = []
for idx, d in enumerate(CANONICAL_DYNASTIES, start=1):
    dynasty_id_map[d["name_en"]] = idx
    dynasty_rows.append({
        'id': idx,
        'name_zh': d["name_zh"],
        'name_en': d["name_en"],
        'start_year': d["start_year"],
        'end_year': d["end_year"],
        'description': None,
        'created_at': CRAWL_DATE,
    })
df_dynasties = pd.DataFrame(dynasty_rows)

artist_raw_list = df['作者'].dropna().unique().tolist()
artist_id_map = {}
artist_rows = []
artist_id = 1
for a in artist_raw_list:
    a_str = str(a).strip()
    if not a_str or a_str.lower() in ('artist/maker unknown', 'unknown'):
        continue
    artist_id_map[a_str] = artist_id
    artist_rows.append({
        'id': artist_id,
        'name_zh': None,
        'name_en': a_str,
        'birth_year': None,
        'death_year': None,
        'dynasty_id': None,
        'biography': None,
        'baidu_url': None,
        'wiki_url': None,
        'created_at': CRAWL_DATE,
        'updated_at': CRAWL_DATE,
    })
    artist_id += 1
df_artists = pd.DataFrame(artist_rows)

df_artifacts = df.copy()
df_artifacts['object_id'] = df_artifacts['藏品编号'].astype(str)
df_artifacts['title_en'] = df_artifacts['藏品名称'].astype(str).str.strip()
df_artifacts['title_en'] = df_artifacts['title_en'].replace('', 'unknown')
df_artifacts['title_zh'] = None
df_artifacts['time_period'] = df_artifacts['时间'].astype(str).str.strip()
df_artifacts['time_period'] = df_artifacts['time_period'].replace('nan', None)

df_artifacts['dynasty_id'] = df_artifacts['朝代'].apply(
    lambda x: dynasty_id_map.get(match_dynasty(x), None)
    if pd.notna(x) else None
)

df_artifacts['type'] = df_artifacts['类别'].astype(str).str.strip()
df_artifacts['material'] = df_artifacts['媒介'].astype(str).str.strip()
df_artifacts['material'] = df_artifacts['material'].replace('nan', None)
df_artifacts['description'] = df_artifacts['摘要'].astype(str).str.strip()
df_artifacts['description'] = df_artifacts['description'].replace('nan', None)
df_artifacts['dimensions'] = df_artifacts['尺寸'].astype(str).str.strip()
df_artifacts['dimensions'] = df_artifacts['dimensions'].replace('nan', None)
df_artifacts['museum_id'] = MUSEUM_ID
df_artifacts['location_id'] = None
df_artifacts['detail_url'] = df_artifacts['详情链接'].astype(str).str.strip()
df_artifacts['image_url'] = df_artifacts['图片链接'].astype(str).str.strip()
df_artifacts['image_path'] = None
df_artifacts['credit_line'] = df_artifacts['信用信息'].astype(str).str.strip()
df_artifacts['credit_line'] = df_artifacts['credit_line'].replace('nan', None)
df_artifacts['accession_number'] = df_artifacts['藏品编号'].astype(str)
df_artifacts['crawl_date'] = CRAWL_DATE
df_artifacts['image_validated'] = None
df_artifacts['last_updated'] = CRAWL_DATE
df_artifacts['created_at'] = CRAWL_DATE

df_artifacts['id'] = range(1, len(df_artifacts) + 1)

df_artifacts_out = df_artifacts[[
    'id', 'object_id', 'title_zh', 'title_en', 'time_period', 'dynasty_id',
    'type', 'material', 'description', 'dimensions', 'museum_id', 'location_id',
    'detail_url', 'image_url', 'image_path', 'credit_line', 'accession_number',
    'crawl_date', 'image_validated', 'last_updated', 'created_at',
]].copy()

mask_valid_url = (
    df_artifacts_out['detail_url'].notna()
    & (df_artifacts_out['detail_url'] != '')
    & df_artifacts_out['image_url'].notna()
    & (df_artifacts_out['image_url'] != '')
)
df_artifacts_out = df_artifacts_out[mask_valid_url].reset_index(drop=True)
df_artifacts_out['id'] = range(1, len(df_artifacts_out) + 1)

object_id_to_artifact_id = dict(
    zip(df_artifacts_out['object_id'], df_artifacts_out['id'])
)

image_rows = []
img_id = 1
for _, row in df_artifacts_out.iterrows():
    url = row['image_url']
    if pd.notna(url) and str(url).strip():
        image_rows.append({
            'id': img_id,
            'artifact_id': row['id'],
            'image_url': str(url).strip(),
            'image_path': None,
            'is_primary': 1,
            'sort_order': 1,
        })
        img_id += 1
df_artifact_images = pd.DataFrame(image_rows)

aa_rows = []
for _, row in df.iterrows():
    artist_raw = str(row['作者']).strip()
    obj_id = str(row['藏品编号'])
    artifact_id = object_id_to_artifact_id.get(obj_id)
    if artifact_id is None:
        continue
    if artist_raw.lower() in ('artist/maker unknown', 'unknown', 'nan', ''):
        continue
    artist_id_val = artist_id_map.get(artist_raw)
    if artist_id_val is not None:
        aa_rows.append({
            'artifact_id': artifact_id,
            'artist_id': artist_id_val,
            'relationship_type': 'creator',
        })
df_artifact_artist = pd.DataFrame(aa_rows)

museum_row.to_csv(f"{OUTPUT_DIR}/clean_museums.csv", index=False, encoding='utf-8-sig')
df_dynasties.to_csv(f"{OUTPUT_DIR}/clean_dynasties.csv", index=False, encoding='utf-8-sig')
df_artists.to_csv(f"{OUTPUT_DIR}/clean_artists.csv", index=False, encoding='utf-8-sig')
df_artifacts_out.to_csv(f"{OUTPUT_DIR}/clean_artifacts.csv", index=False, encoding='utf-8-sig')
df_artifact_images.to_csv(f"{OUTPUT_DIR}/clean_artifact_images.csv", index=False, encoding='utf-8-sig')
df_artifact_artist.to_csv(f"{OUTPUT_DIR}/clean_artifact_artist.csv", index=False, encoding='utf-8-sig')

print(f"✅ 数据清洗完成，共生成 6 个CSV文件：")
print(f"   - clean_museums.csv       ({len(museum_row)} 条)")
print(f"   - clean_dynasties.csv     ({len(df_dynasties)} 条)")
print(f"   - clean_artists.csv       ({len(df_artists)} 条)")
print(f"   - clean_artifacts.csv     ({len(df_artifacts_out)} 条)")
print(f"   - clean_artifact_images.csv ({len(df_artifact_images)} 条)")
print(f"   - clean_artifact_artist.csv ({len(df_artifact_artist)} 条)")
