"""
费城艺术博物馆爬虫 - 支持增量爬取

增量爬取策略：
- 以 UUID (藏品编号) 作为记录唯一标识
- 首次全量爬取，后续仅爬取新增或更新的记录
- 通过对比搜索结果的 UUID 列表快速识别新增文物
- 对已有记录重新请求详情以检测字段更新
- 每次爬取结束后记录变更日志
"""
import os
import sys
import csv
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from incremental import IncrementalTracker, CrawlLogger, IncrementalCSVWriter

import requests
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


PHILA_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(PHILA_DIR, "Philamuseum_chinese_made_artworks_final.csv")
UUID_CACHE_FILE = os.path.join(PHILA_DIR, ".phila_uuids.json")

url = 'https://prod.philamuseumsearch.org/v1/search'
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
}


def create_session():
    """创建带重试机制的 session"""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    return session


def get_object_details(uuid, session):
    """获取文物详情"""
    detail_url = f'https://pma-collection.web.app/gen2/v1/objects/{uuid}'
    try:
        response = session.get(detail_url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"获取详情失败: {uuid} - {e}")
    return {}


def fetch_artwork_data(item, session, processed_uuids, failed_uuids, tracker):
    """获取并组装文物完整信息，同时进行增量检测"""
    constituents = item.get('constituents', '')
    uuid = item.get('uuid', '')

    if uuid in processed_uuids:
        return None, 'unchanged'

    processed_uuids.add(uuid)

    if isinstance(constituents, str) and 'Chinese' in constituents:
        details = get_object_details(uuid, session)
        if not details:
            failed_uuids.add(uuid)
            return None, 'failed'

        dimensions = details.get('Dimensions', '')
        credit_line = details.get('CreditLine', '')
        medium = details.get('Medium', '')
        dynasty = details.get('Dynasty', '')

        image_url = item.get('imageUrl', '')
        if image_url and not image_url.startswith("http"):
            image_url = f"https://iiif.micr.io/{image_url}/full/^300,/0/default.jpg"

        record = {
            '藏品编号': uuid,
            '藏品名称': item.get('title', ''),
            '作者': item.get('artist', ''),
            '时间': item.get('date', ''),
            '朝代': dynasty,
            '类别': item.get('category', ''),
            '尺寸': dimensions,
            '媒介': medium,
            '摘要': item.get('summary', ''),
            '信用信息': credit_line,
            '图片链接': image_url if image_url.startswith("http") else '',
            '详情链接': f'https://www.philamuseum.org/collection/object/{uuid}',
        }

        # 增量检测
        change_type = tracker.check(uuid, record)
        return record, change_type

    return None, 'skipped'


def load_cached_uuids():
    """加载上次缓存的 UUID 列表"""
    if os.path.exists(UUID_CACHE_FILE):
        try:
            with open(UUID_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return set(data.get('uuids', []))
        except Exception:
            pass
    return set()


def save_cached_uuids(uuids):
    """保存 UUID 列表缓存"""
    with open(UUID_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump({'uuids': sorted(list(uuids)), 'saved_at': time.strftime('%Y-%m-%d %H:%M:%S')}, f)


def save_data_to_csv(data, path):
    """保存数据到 CSV"""
    if not data:
        return
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    file_exists = os.path.exists(path) and os.path.getsize(path) > 0
    fieldnames = list(data[0].keys())

    with open(path, mode='a', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(data)


def run_incremental():
    """增量爬取主函数"""
    tracker = IncrementalTracker(PHILA_DIR)
    logger = CrawlLogger(PHILA_DIR)

    last_crawl = tracker.last_crawl_time
    if last_crawl:
        print(f"上次爬取时间: {last_crawl}")
        print(f"历史指纹数: {len(tracker.fingerprints)}")
    else:
        print("首次爬取，将全量获取数据")

    cached_uuids = load_cached_uuids()
    print(f"缓存 UUID 数: {len(cached_uuids)}")

    processed_uuids = set()
    failed_uuids = set()
    session = create_session()

    new_records = []
    updated_records = []

    from_ = 0
    all_current_uuids = set()

    with ThreadPoolExecutor(max_workers=10) as executor:
        while True:
            page_num = (from_ + 48) // 48
            print(f'\n正在爬取第{page_num}页')

            payload = {
                'query': 'chinese',
                'paging': {'from': from_, 'size': 48}
            }

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
                result = resp.json().get('result', [])
            except Exception as e:
                print(f'请求失败或解析出错：{e}')
                break

            if not result:
                print('所有信息已被爬取')
                break

            # 收集当前页 UUID
            for item in result:
                uuid = item.get('uuid', '')
                if uuid:
                    all_current_uuids.add(uuid)

            # 并发获取详情
            results = list(executor.map(
                fetch_artwork_data,
                result,
                [session] * len(result),
                [processed_uuids] * len(result),
                [failed_uuids] * len(result),
                [tracker] * len(result)
            ))

            # 分类处理
            page_new = []
            page_updated = []
            for record, change_type in results:
                if record is None:
                    continue
                if change_type == 'new':
                    page_new.append(record)
                elif change_type == 'updated':
                    page_updated.append(record)

            # 保存新增记录
            if page_new:
                save_data_to_csv(page_new, CSV_FILE)
                new_records.extend(page_new)
                print(f'  [+] 第{page_num}页新增: {len(page_new)}条')

            # 保存更新记录（追加到CSV，后续由清洗流程处理）
            if page_updated:
                save_data_to_csv(page_updated, CSV_FILE)
                updated_records.extend(page_updated)
                print(f'  [~] 第{page_num}页更新: {len(page_updated)}条')

            unchanged_count = sum(1 for _, ct in results if ct == 'unchanged')
            if unchanged_count > 0:
                print(f'  [=] 第{page_num}页未变化: {unchanged_count}条')

            from_ += 48
            time.sleep(1)

    # 重试失败的文物
    if failed_uuids:
        print(f"\n重试失败的文物，当前失败数: {len(failed_uuids)}")
        for uuid in list(failed_uuids):
            details = get_object_details(uuid, session)
            if details:
                failed_uuids.remove(uuid)
                print(f"文物 {uuid} 重试成功")

    # 更新 UUID 缓存
    save_cached_uuids(all_current_uuids)

    # 保存指纹和日志
    tracker.save()
    stats = tracker.get_stats()
    logger.log(stats)
    logger.print_summary(stats)


if __name__ == "__main__":
    run_incremental()
