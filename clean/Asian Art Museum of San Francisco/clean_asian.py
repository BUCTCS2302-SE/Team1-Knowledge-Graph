import csv, re
from datetime import date
from collections import Counter

today = date.today().isoformat()
BASE = r'e:\软工\spider\Asian Art Museum of San Francisco'

# ===== 读取原始数据 =====
# 尝试多种编码，优先utf-8-sig，回退gbk
for enc in ['utf-8-sig', 'gbk', 'utf-8']:
    try:
        with open(BASE + r'\objects_china_verified_dedup.csv', 'r', encoding=enc) as f:
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

# ===== Step 2: 仅保留中国文物 =====
# 通过Department字段过滤，只保留Chinese Art
before_count = len(rows)
rows = [r for r in rows if r.get('Department', '').strip() == 'Chinese Art']
print('Step2 - 仅保留Chinese Art后:', len(rows), '(剔除非中国文物:', before_count - len(rows), ')')

# ===== Step 3: 无图片行去除 =====
rows = [r for r in rows if r['image_url'].strip()]
print('Step3 - 去除无图片后:', len(rows))

# ===== Step 4: 详情页URL去重 =====
seen = set()
deduped = []
for r in rows:
    key = r['detail_url'].strip()
    if key and key not in seen:
        seen.add(key)
        deduped.append(r)
rows = deduped
print('Step4 - 详情页URL去重后:', len(rows))

# ===== Step 5: 关键字段完整性检查 + Date清洗 =====
def clean_date(date_str):
    """清洗日期字段：去除approx./Approx./before等前缀，返回清洗后的日期字符串"""
    s = date_str.strip()
    if not s:
        return ''
    # 去除常见前缀
    s = re.sub(r'^(approx\.\s*|Approx\.\s*|about\s*|ca\.\s*|c\.\s*|before\s*)', '', s, flags=re.IGNORECASE)
    return s.strip()

def has_valid_date(date_str):
    """检查清洗后的日期是否以数字开头（含负数年份）"""
    cleaned = clean_date(date_str)
    if not cleaned:
        return False
    return bool(re.match(r'^[-\d]', cleaned))

filtered = []
for r in rows:
    obj_num = r['Object number'].strip()
    title = r['Title'].strip()
    date_val = r['Date'].strip()
    medium = r['Materials'].strip() if r['Materials'].strip() else r['Medium'].strip()
    img_url = r['image_url'].strip()

    if not all([obj_num, title, date_val, medium, img_url]):
        continue
    if not has_valid_date(date_val):
        continue
    filtered.append(r)
rows = filtered
print('Step5 - 字段完整(Artist可空)+Date有效后:', len(rows))

# ===== Step 6: 匹配dynasty_id =====
# 读取朝代表
dynasty_map = {}
with open(r'e:\软工\database\philamuseum\clean_dynasties.csv', 'r', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        dynasty_map[r['name_en'].lower().strip()] = int(r['id'])

# 非中国时期关键词（不应映射到中国朝代）
NON_CHINESE_PERIODS = {
    'edo', 'muromachi', 'momoyama', 'heian', 'nara', 'kamakura',
    'ashikaga', 'kofun', 'jomon', 'yayoi', 'meiji', 'taisho',
    'showa', 'heisei', 'reiwa', 'joseon', 'goryeo',
}

def match_dynasty_id(dynasty_str, period_str, date_str):
    """匹配朝代ID，仅匹配中国朝代"""
    # 优先从Dynasty字段匹配
    for field in [dynasty_str, period_str]:
        field = field.strip()
        if not field:
            continue
        fl = field.lower()

        # 先检查是否为非中国时期，如果是则返回None
        for np in NON_CHINESE_PERIODS:
            if np in fl:
                return None

        # 直接匹配朝代表
        for name, did in dynasty_map.items():
            if name in fl:
                return did

        # 中国朝代特殊匹配
        if 'warring states' in fl:
            return 4  # 东周
        if 'spring and autumn' in fl:
            return 4  # 东周
        if 'eastern zhou' in fl:
            return 4
        if 'western zhou' in fl:
            return 3
        if 'three kingdoms' in fl:
            return 10  # 六朝
        if 'neolithic' in fl:
            return None
        if 'republic period' in fl or 'republic of china' in fl or 'chinese republic' in fl:
            return 28
        if 'republic' in fl and 'korea' not in fl:
            return 28

        break  # 只检查Dynasty，不重复检查Period

    # 从Date字段解析年份（使用清洗后的日期）
    ds = clean_date(date_str)
    # 提取年份范围
    m = re.match(r'(\d+)\s*[-–—]\s*(\d+)', ds)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y1 > 100 and y2 > 100:
            mid = (y1 + y2) / 2
            return year_to_dynasty(mid)
    # 单个年份
    m = re.match(r'^[-]?(\d{3,4})', ds)
    if m:
        y = int(m.group(0))
        return year_to_dynasty(y)
    return None

def year_to_dynasty(year):
    if year >= 1912: return 28  # 中华民国
    if year >= 1644: return 27  # 清朝
    if year >= 1368: return 26  # 明朝
    if year >= 1271: return 25  # 元朝
    if year >= 1127: return 23  # 南宋
    if year >= 960: return 22   # 北宋
    if year >= 907: return 19   # 五代
    if year >= 618: return 18   # 唐朝
    if year >= 581: return 17   # 隋朝
    if year >= 386: return 13   # 北朝
    if year >= 317: return 14   # 南朝
    if year >= 220: return 10   # 六朝
    if year >= 25: return 9     # 东汉
    if year >= -206: return 7   # 汉朝
    if year >= -770: return 4   # 东周
    if year >= -1100: return 3  # 西周
    return None

# 匹配朝代
matched = []
unmatched_count = 0
for r in rows:
    did = match_dynasty_id(r['Dynasty'], r['Period'], r['Date'])
    if did is not None:
        r['_dynasty_id'] = did
        matched.append(r)
    else:
        unmatched_count += 1
rows = matched
print('Step6 - 匹配朝代后:', len(rows), '(未匹配:', unmatched_count, ')')

# ===== Step 7: 生成最终CSV =====
start_id = 5527  # 接续大都会博物馆最后一条
out_cols = ['object_id', 'title_zh', 'title_en', 'time_period', 'dynasty_id', 'type',
            'material', 'description', 'dimensions', 'museum_id', 'location_id',
            'detail_url', 'image_url', 'image_path', 'credit_line', 'accession_number',
            'crawl_date', 'image_validated', 'last_updated', 'created_at']

out_rows = []
for i, r in enumerate(rows):
    # 构建description：组合Materials/Medium和Dynasty/Period信息
    material = r['Materials'].strip() if r['Materials'].strip() else r['Medium'].strip()
    dynasty_info = r['Dynasty'].strip() or r['Period'].strip()
    description = material
    if dynasty_info:
        description = f"{dynasty_info}; {material}"

    out_rows.append({
        'object_id': str(start_id + i),
        'title_zh': '',
        'title_en': r['Title'].strip(),
        'time_period': clean_date(r['Date']),
        'dynasty_id': str(r['_dynasty_id']),
        'type': r['Classifications'].strip(),
        'material': material,
        'description': description,
        'dimensions': r['Dimensions'].strip(),
        'museum_id': '2',
        'location_id': r['Place of Origin'].strip(),
        'detail_url': r['detail_url'].strip(),
        'image_url': r['image_url'].strip(),
        'image_path': '',
        'credit_line': r['Credit Line'].strip(),
        'accession_number': r['Object number'].strip(),
        'crawl_date': today,
        'image_validated': '1',
        'last_updated': '',
        'created_at': ''
    })

out_path = BASE + r'\asian_final.csv'
with open(out_path, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=out_cols)
    w.writeheader()
    w.writerows(out_rows)

print()
print('===== 清洗完成 =====')
print('最终行数:', len(out_rows))
print('object_id范围:', start_id, '~', start_id + len(out_rows) - 1)

# 朝代分布
dyn_dist = Counter(r['_dynasty_id'] for r in rows)
dyn_names = {2:'周朝',3:'西周',4:'东周',6:'秦朝',7:'汉朝',8:'西汉',9:'东汉',
             10:'六朝',12:'南北朝',13:'北朝',14:'南朝',15:'北魏',16:'北齐',
             17:'隋朝',18:'唐朝',19:'五代',20:'辽朝',21:'宋朝',22:'北宋',
             23:'南宋',24:'金朝',25:'元朝',26:'明朝',27:'清朝',28:'中华民国'}
print()
print('朝代分布:')
for did, cnt in sorted(dyn_dist.items(), key=lambda x: -x[1]):
    print(f'  {dyn_names.get(did, did)} (id={did}): {cnt}')
