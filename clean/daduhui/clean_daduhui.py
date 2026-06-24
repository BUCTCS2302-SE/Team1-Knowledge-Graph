import csv, re
from datetime import date
from collections import Counter

today = date.today().isoformat()
BASE = r'e:\软工\spider\daduhui'

# ===== 读取原始数据 =====
for enc in ['utf-8-sig', 'utf-8', 'gbk']:
    try:
        with open(BASE + r'\daduihui_en.csv', 'r', encoding=enc) as f:
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

# ===== Step 2: 去除无图片记录 =====
before_count = len(rows)
rows = [r for r in rows if r.get('Image', '').strip() and r['Image'].strip() != 'no_image']
print('Step2 - 去除无图片后:', len(rows), '(剔除:', before_count - len(rows), ')')

# ===== Step 3: 关键字段完整性检查 =====
filtered = []
for r in rows:
    title = r.get('Title', '').strip()
    period = r.get('Period', '').strip()
    img_url = r.get('Image', '').strip()
    obj_url = r.get('Object URL', '').strip()

    if not all([title, period, img_url]):
        continue
    filtered.append(r)
rows = filtered
print('Step3 - 关键字段完整后:', len(rows))

# ===== Step 4: 详情页URL去重 =====
seen = set()
deduped = []
for r in rows:
    key = r.get('Object URL', '').strip()
    if key and key not in seen:
        seen.add(key)
        deduped.append(r)
rows = deduped
print('Step4 - 详情页URL去重后:', len(rows))

# ===== Step 5: 匹配dynasty_id =====
# 读取朝代表
dynasty_map = {}
with open(r'e:\软工\database\philamuseum\clean_dynasties.csv', 'r', encoding='utf-8-sig') as f:
    for dr in csv.DictReader(f):
        dynasty_map[dr['name_en'].lower().strip()] = int(dr['id'])

def parse_period_to_years(period_str):
    """
    解析Period字段为年份范围，返回dynasty_id或None。
    支持格式：
    - "1800–1900", "1825–45"
    - "ca. 1897", "ca. 1860–66"
    - "18th century", "19th–20th century"
    - "late 18th century", "early 19th century"
    - "late 18th–early 19th century"
    - "16th–19th century"
    """
    s = period_str.strip()
    if not s:
        return None

    # 去除前缀
    s_clean = re.sub(r'^(ca\.\s*|about\s*|c\.\s*)', '', s, flags=re.IGNORECASE).strip()

    # 格式1: "late/early/mid Xth century" 或 "Xth century"
    # 也支持 "late 18th–early 19th century" 和 "16th–19th century"
    century_match = re.match(
        r'(?:(late|early|mid)\s+)?(\d{1,2})(?:st|nd|rd|th)\s*century'
        r'(?:\s*[–\-—]\s*(?:(late|early|mid)\s+)?(\d{1,2})(?:st|nd|rd|th)\s*century)?',
        s_clean, re.IGNORECASE
    )
    if century_match:
        qual1, c1, qual2, c2 = century_match.groups()
        c1 = int(c1)
        if qual2 and c2:
            c2 = int(c2)
            y1 = century_to_year(c1, qual1)
            y2 = century_to_year(c2, qual2)
        else:
            y1 = century_to_year(c1, qual1)
            y2 = y1 + 99
        mid = (y1 + y2) / 2
        return year_to_dynasty(mid)

    # 格式2: "late/early/mid Xth–Yth century" (跨世纪带修饰词)
    cross_century = re.match(
        r'(?:(late|early|mid)\s+)?(\d{1,2})(?:st|nd|rd|th)\s*[–\-—]\s*'
        r'(?:(late|early|mid)\s+)?(\d{1,2})(?:st|nd|rd|th)\s*century',
        s_clean, re.IGNORECASE
    )
    if cross_century:
        qual1, c1, qual2, c2 = cross_century.groups()
        y1 = century_to_year(int(c1), qual1)
        y2 = century_to_year(int(c2), qual2)
        mid = (y1 + y2) / 2
        return year_to_dynasty(mid)

    # 格式3: 年份范围 "1800–1900", "1825–45"
    range_match = re.match(r'(\d{3,4})\s*[–\-—]\s*(\d{2,4})', s_clean)
    if range_match:
        y1 = int(range_match.group(1))
        y2_str = range_match.group(2)
        y2 = int(y2_str)
        # 处理缩写年份如 "1825–45" → 1845
        if len(y2_str) <= 2:
            y2 = y1 // 100 * 100 + y2
        if y1 > 100 and y2 > 100:
            mid = (y1 + y2) / 2
            return year_to_dynasty(mid)

    # 格式4: 单个年份 "1897"
    single_match = re.match(r'^(\d{3,4})', s_clean)
    if single_match:
        y = int(single_match.group(1))
        return year_to_dynasty(y)

    return None

def century_to_year(century_num, qualifier=None):
    """将世纪编号转为大致年份，如 19th century → 1850"""
    base = (century_num - 1) * 100
    if qualifier and qualifier.lower() in ('late',):
        return base + 75
    elif qualifier and qualifier.lower() in ('early',):
        return base + 25
    elif qualifier and qualifier.lower() in ('mid',):
        return base + 50
    return base + 50  # 默认取世纪中点

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
    did = parse_period_to_years(r.get('Period', ''))
    if did is not None:
        r['_dynasty_id'] = did
        matched.append(r)
    else:
        unmatched_count += 1
rows = matched
print('Step5 - 匹配朝代后:', len(rows), '(未匹配:', unmatched_count, ')')

# ===== Step 6: 生成最终CSV =====
start_id = 2501  # 大都会博物馆起始ID
out_cols = ['object_id', 'title_zh', 'title_en', 'time_period', 'dynasty_id', 'type',
            'material', 'description', 'dimensions', 'museum_id', 'location_id',
            'detail_url', 'image_url', 'image_path', 'credit_line', 'accession_number',
            'crawl_date', 'image_validated', 'last_updated', 'created_at']

out_rows = []
for i, r in enumerate(rows):
    title_en = r['Title'].strip()
    material = r.get('Medium', '').strip()
    # material为unknown时留空
    if material.lower() == 'unknown':
        material = ''

    # 根据材质推断文物类型
    type_en = ''
    mat_lower = material.lower()
    if any(kw in mat_lower for kw in ['porcelain', 'ceramic', 'stoneware', 'earthenware', 'pottery']):
        type_en = 'Ceramics'
    elif any(kw in mat_lower for kw in ['silk', 'textile', 'fabric', 'embroidery', 'tapestry', 'satin', 'linen', 'cotton']):
        type_en = 'Textiles'
    elif any(kw in mat_lower for kw in ['jade', 'nephrite', 'jadeite']):
        type_en = 'Jade'
    elif any(kw in mat_lower for kw in ['lacquer', 'lacquered']):
        type_en = 'Lacquer'
    elif any(kw in mat_lower for kw in ['bronze', 'copper', 'brass', 'iron', 'steel', 'gold', 'silver', 'metal']):
        type_en = 'Metalwork'
    elif any(kw in mat_lower for kw in ['wood', 'bamboo', 'ivory', 'bone', 'horn']):
        type_en = 'Decorative Arts'
    elif any(kw in mat_lower for kw in ['painting', 'ink', 'watercolor', 'gouache', 'oil']):
        type_en = 'Paintings'
    elif any(kw in mat_lower for kw in ['glass', 'enamel']):
        type_en = 'Glass'
    elif any(kw in mat_lower for kw in ['paper', 'scroll', 'silk']):
        type_en = 'Paintings'
    elif mat_lower:
        type_en = 'Decorative Arts'

    out_rows.append({
        'object_id': str(start_id + i),
        'title_zh': '',  # 翻译部分不处理
        'title_en': title_en,
        'time_period': r.get('Period', '').strip(),
        'dynasty_id': str(r['_dynasty_id']),
        'type': type_en,
        'material': material,
        'description': material,
        'dimensions': '',
        'museum_id': '1',
        'location_id': '',
        'detail_url': r.get('Object URL', '').strip(),
        'image_url': r.get('Image', '').strip(),
        'image_path': '',
        'credit_line': '',
        'accession_number': '',
        'crawl_date': today,
        'image_validated': '1',
        'last_updated': '',
        'created_at': ''
    })

out_path = r'e:\软工\clean\daduhui\daduhui_final.csv'
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
