import pandas as pd
import re
import os
import shutil

df = pd.read_csv('clean_artifacts_translated.csv')

def clean_html(text):
    if pd.isna(text):
        return text
    text = str(text)
    text = re.sub(r'<p[^>]*>\s*</p>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.strip()
    return text if text else None

for col in ['description', 'description_zh']:
    before = df[col].dropna().apply(lambda x: bool(re.search(r'<[^>]+>', str(x)))).sum()
    df[col] = df[col].apply(clean_html)
    after = df[col].dropna().apply(lambda x: bool(re.search(r'<[^>]+>', str(x)))).sum()
    print(f'{col}: {before} -> {after} 条含HTML')

tmp1 = 'clean_artifacts_translated_tmp.csv'
df.to_csv(tmp1, index=False, encoding='utf-8-sig')

df_art = df.drop(columns=['title_zh', 'material_zh', 'type_zh', 'description_zh'], errors='ignore')
tmp2 = 'clean_artifacts_tmp2.csv'
df_art.to_csv(tmp2, index=False, encoding='utf-8-sig')

try:
    os.remove('clean_artifacts_translated.csv')
except PermissionError:
    pass
try:
    os.remove('clean_artifacts.csv')
except PermissionError:
    pass

try:
    shutil.move(tmp1, 'clean_artifacts_translated.csv')
    shutil.move(tmp2, 'clean_artifacts.csv')
    print('✅ CSV 文件已更新')
except Exception as e:
    print(f'⚠️ 替换失败: {e}')
    print(f'临时文件: {tmp1}, {tmp2}')
    print('请关闭IDE中的CSV后手动重命名')
