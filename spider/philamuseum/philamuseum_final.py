import os
import csv
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

url = 'https://prod.philamuseumsearch.org/v1/search'
file_path = 'Philamuseum_chinese_made_artworks_final.csv'
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
}

# 创建一个带有重试机制的 session
def create_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])  # 重试机制：最多3次
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    return session


# 保存数据到 CSV 文件
def save_data_to_csv(data: list, path: str):
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    file_exists = os.path.exists(path)
    write_header = not file_exists or (file_exists and os.path.getsize(path) == 0)

    fieldnames = list(data[0].keys())
    with open(path, mode='a', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(data)


# 获取文物详情页面中的信息
def get_object_details(uuid: str, session):
    detail_url = f'https://pma-collection.web.app/gen2/v1/objects/{uuid}'
    try:
        response = session.get(detail_url, timeout=5)  # 设置5秒超时
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"获取详情失败: {uuid} - {e}")
    return {}


# 获取文物信息
def fetch_artwork_data(item, session, processed_uuids, failed_uuids):
    # 判断文物的"constituents"字段是否包含"Chinese"
    constituents = item.get('constituents', '')
    uuid = item.get('uuid', '')

    # 如果该文物已经被处理过，跳过
    if uuid in processed_uuids:
        return None

    # 标记为已处理
    processed_uuids.add(uuid)

    if isinstance(constituents, str) and 'Chinese' in constituents:
        # 获取详情页面的内容
        details = get_object_details(uuid, session)

        # 如果获取失败，将该uuid添加到失败列表
        if not details:
            failed_uuids.add(uuid)
            return None

        dimensions = details.get('Dimensions', '')
        credit_line = details.get('CreditLine', '')
        medium = details.get('Medium', '')
        dynasty = details.get('Dynasty', '')

        # 处理图片链接，如果是相对路径则拼接完整URL
        image_url = item.get('imageUrl', '')
        if image_url and not image_url.startswith("http"):
            image_url = f"https://iiif.micr.io/{image_url}/full/^300,/0/default.jpg"

        return {
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

    return None


# 重试获取失败的文物
def retry_failed_uuids(failed_uuids, session):
    for uuid in list(failed_uuids):
        print(f"正在重试文物: {uuid}")
        details = get_object_details(uuid, session)
        if details:
            failed_uuids.remove(uuid)
            print(f"文物 {uuid} 重试成功")
        else:
            print(f"文物 {uuid} 重试失败")


from_ = 0
processed_uuids = set()  # 用于存储已处理的 uuid
failed_uuids = set()  # 用于存储获取失败的 uuid
session = create_session()  # 创建带重试机制的 session

# 使用 ThreadPoolExecutor 来加速
with ThreadPoolExecutor(max_workers=10) as executor:
    while True:
        print(f'正在爬取第{(from_ + 48) // 48}页')
        payload = {
            'query': 'chinese',
            'paging': {
                'from': from_,
                'size': 48,
            }
        }
        resp = requests.post(url, headers=headers, json=payload)

        try:
            result = resp.json().get('result', [])
        except Exception as e:
            print(f'请求失败或解析出错：{e}')
            break

        # 如果没有更多数据，跳出循环
        if not result:
            print('所有信息已被爬取')
            break

        # 使用并发来获取每个文物的详情信息
        datalist = list(
            executor.map(fetch_artwork_data, result, [session] * len(result), [processed_uuids] * len(result),
                         [failed_uuids] * len(result)))

        # 过滤掉 None 的项
        datalist = [data for data in datalist if data is not None]

        if datalist:
            save_data_to_csv(datalist, file_path)
            print(f'第{(from_ + 48) // 48}页信息已保存')
        else:
            print(f'第{(from_ + 48) // 48}页没有符合条件的数据')

        from_ += 48
        time.sleep(1)

        # 重试获取失败的文物
        if failed_uuids:
            print(f"重试失败的文物，当前失败数: {len(failed_uuids)}")
            retry_failed_uuids(failed_uuids, session)
            if not failed_uuids:
                print("所有失败的文物已成功获取")