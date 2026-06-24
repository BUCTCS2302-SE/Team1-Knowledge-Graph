import csv, re
from datetime import date
from collections import Counter

today = date.today().isoformat()
BASE = r'e:\软工\spider\philamuseum'
MUSEUM_ID = 3  # 费城艺术博物馆在museums表中的id

# ===== 读取原始数据 =====
for enc in ['utf-8-sig', 'utf-8', 'gbk']:
    try:
        with open(BASE + r'\Philamuseum_chinese_made_artworks_final.csv', 'r', encoding=enc) as f:
            raw_rows = list(csv.DictReader(f))
        print(f'使用编码: {enc}')
        break
    except (UnicodeDecodeError, UnicodeError):
        continue
else:
    raise RuntimeError('无法识别文件编码')

cols = list(raw_rows[0].keys())
print('原始行数:', len(raw_rows))

# ===== Step 1: 完全重复去重 =====
seen = set()
unique = []
dup_count = 0
for r in raw_rows:
    key = tuple(r[c] for c in cols)
    if key not in seen:
        seen.add(key)
        unique.append(r)
    else:
        dup_count += 1
rows = unique
print('Step1 - 完全重复去重后:', len(rows), '(剔除:', dup_count, ')')

# ===== Step 2: 去除无图片或无详情链接的记录 =====
before_count = len(rows)
rows = [r for r in rows if r.get('图片链接', '').strip() and r.get('详情链接', '').strip()]
print('Step2 - 去除无图片/详情链接后:', len(rows), '(剔除:', before_count - len(rows), ')')

# ===== Step 3: 关键字段完整性检查 =====
filtered = []
for r in rows:
    title = r.get('藏品名称', '').strip()
    period = r.get('时间', '').strip()
    dynasty = r.get('朝代', '').strip()
    medium = r.get('媒介', '').strip()
    img_url = r.get('图片链接', '').strip()
    detail_url = r.get('详情链接', '').strip()

    if not all([title, period, dynasty, medium, img_url, detail_url]):
        continue
    filtered.append(r)
rows = filtered
print('Step3 - 关键字段完整后:', len(rows))

# ===== Step 3.5: 详情页URL去重 =====
seen = set()
deduped = []
for r in rows:
    key = r.get('详情链接', '').strip()
    if key and key not in seen:
        seen.add(key)
        deduped.append(r)
rows = deduped
print('Step3.5 - 详情页URL去重后:', len(rows))

# ===== Step 4: HTML标签清洗 =====
def clean_html(text):
    """去除HTML标签，保留文本内容"""
    if not text or not text.strip():
        return ''
    text = re.sub(r'<p[^>]*>\s*</p>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.strip()
    return text

html_cleaned_count = 0
for r in rows:
    desc = r.get('摘要', '').strip()
    if desc and re.search(r'<[^>]+>', desc):
        r['摘要'] = clean_html(desc)
        html_cleaned_count += 1
print('Step4 - HTML清洗:', html_cleaned_count, '条')

# ===== Step 5: 匹配dynasty_id =====
# 朝代映射表（与database/philamuseum/clean_dynasties.csv一致）
DYNASTY_MAP = {
    'Shang Dynasty': 1,
    'Zhou Dynasty': 2,
    'Western Zhou Dynasty': 3,
    'Eastern Zhou Dynasty': 4,
    'Warring States Period': 5,
    'Qin Dynasty': 6,
    'Han Dynasty': 7,
    'Western Han Dynasty': 8,
    'Eastern Han Dynasty': 9,
    'Six Dynasties Period': 10,
    'Western Jin Dynasty': 11,
    'Northern and Southern Dynasties': 12,
    'Northern Dynasties': 13,
    'Southern Dynasties': 14,
    'Northern Wei Dynasty': 15,
    'Northern Qi Dynasty': 16,
    'Sui Dynasty': 17,
    'Tang Dynasty': 18,
    'Five Dynasties': 19,
    'Liao Dynasty': 20,
    'Song Dynasty': 21,
    'Northern Song Dynasty': 22,
    'Southern Song Dynasty': 23,
    'Jin Dynasty': 24,
    'Yuan Dynasty': 25,
    'Ming Dynasty': 26,
    'Qing Dynasty': 27,
    'Republican Period': 28,
}

# 匹配关键词（优先长匹配，避免"Song"误匹配到"Northern Song"等）
MATCH_KEYWORDS = [
    ('Northern and Southern Dynasties', 'Northern and Southern'),
    ('Northern Song Dynasty', 'Northern Song'),
    ('Southern Song Dynasty', 'Southern Song'),
    ('Western Han Dynasty', 'Western Han'),
    ('Eastern Han Dynasty', 'Eastern Han'),
    ('Western Zhou Dynasty', 'Western Zhou'),
    ('Eastern Zhou Dynasty', 'Eastern Zhou'),
    ('Northern Wei Dynasty', 'Northern Wei'),
    ('Northern Qi Dynasty', 'Northern Qi'),
    ('Northern Dynasties', 'Northern Dynasties'),
    ('Southern Dynasties', 'Southern Dynasties'),
    ('Western Jin Dynasty', 'Western Jin'),
    ('Warring States Period', 'Warring States'),
    ('Six Dynasties Period', 'Six Dynasties'),
    ('Five Dynasties', 'Five Dynasties'),
    ('Republican Period', 'Republican'),
    ('Qing Dynasty', 'Qing'),
    ('Ming Dynasty', 'Ming'),
    ('Yuan Dynasty', 'Yuan'),
    ('Song Dynasty', 'Song'),
    ('Jin Dynasty', 'Jin'),
    ('Tang Dynasty', 'Tang'),
    ('Sui Dynasty', 'Sui'),
    ('Han Dynasty', 'Han'),
    ('Liao Dynasty', 'Liao'),
    ('Zhou Dynasty', 'Zhou'),
    ('Shang Dynasty', 'Shang'),
    ('Qin Dynasty', 'Qin'),
]

def match_dynasty(dynasty_str):
    """从朝代字段匹配dynasty_id"""
    if not dynasty_str or not dynasty_str.strip():
        return None
    raw = dynasty_str.strip().lower()
    raw = raw.replace('northen', 'northern')  # 修正拼写错误
    for canonical_name, keyword in MATCH_KEYWORDS:
        if keyword.lower() in raw:
            return DYNASTY_MAP[canonical_name]
    return None

matched = []
unmatched_count = 0
for r in rows:
    did = match_dynasty(r.get('朝代', ''))
    if did is not None:
        r['_dynasty_id'] = did
        matched.append(r)
    else:
        unmatched_count += 1
rows = matched
print('Step5 - 匹配朝代后:', len(rows), '(未匹配:', unmatched_count, ')')

# ===== Step 6: 生成最终CSV =====
out_cols = ['id', 'object_id', 'title_zh', 'title_en', 'time_period', 'dynasty_id',
            'type', 'material', 'description', 'dimensions', 'museum_id', 'location_id',
            'detail_url', 'image_url', 'image_path', 'credit_line', 'accession_number',
            'crawl_date', 'image_validated', 'last_updated', 'created_at']

out_rows = []
for i, r in enumerate(rows):
    accession = r.get('藏品编号', '').strip()
    desc = r.get('摘要', '').strip()

    out_rows.append({
        'id': accession,
        'object_id': str(i + 1),
        'title_zh': '',  # 翻译部分不处理
        'title_en': r.get('藏品名称', '').strip(),
        'time_period': r.get('时间', '').strip(),
        'dynasty_id': str(r['_dynasty_id']),
        'type': r.get('类别', '').strip(),
        'material': r.get('媒介', '').strip(),
        'description': desc,
        'dimensions': r.get('尺寸', '').strip(),
        'museum_id': str(MUSEUM_ID),
        'location_id': '',
        'detail_url': r.get('详情链接', '').strip(),
        'image_url': r.get('图片链接', '').strip(),
        'image_path': '',
        'credit_line': r.get('信用信息', '').strip(),
        'accession_number': accession,
        'crawl_date': today,
        'image_validated': '',
        'last_updated': today,
        'created_at': today,
    })

out_path = r'e:\软工\clean\philamuseum\clean_artifacts.csv'
with open(out_path, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=out_cols)
    w.writeheader()
    w.writerows(out_rows)

print()
print('===== 清洗完成 =====')
print('最终行数:', len(out_rows))
print('object_id范围: 1 ~', len(out_rows))

# 朝代分布
dyn_dist = Counter(r['_dynasty_id'] for r in rows)
dyn_names = {1:'商朝',2:'周朝',3:'西周',4:'东周',5:'战国',6:'秦朝',7:'汉朝',8:'西汉',9:'东汉',
             10:'六朝',11:'西晋',12:'南北朝',13:'北朝',14:'南朝',15:'北魏',16:'北齐',
             17:'隋朝',18:'唐朝',19:'五代',20:'辽朝',21:'宋朝',22:'北宋',
             23:'南宋',24:'金朝',25:'元朝',26:'明朝',27:'清朝',28:'中华民国'}
print()
print('朝代分布:')
for did, cnt in sorted(dyn_dist.items(), key=lambda x: -x[1]):
    print(f'  {dyn_names.get(did, did)} (id={did}): {cnt}')
