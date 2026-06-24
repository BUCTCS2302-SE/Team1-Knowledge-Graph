import requests
import hashlib
import random
import re
import pandas as pd
import time
import os
from tqdm import tqdm

appid = "" # 百度翻译 API 应用ID
secret_key = "" # 百度翻译 API 密钥

MAX_RETRIES = 3
RETRY_DELAY = 2
BATCH_SIZE = 30
SLEEP_TIME = 1.0
MAX_QUERY_CHARS = 5500
MAX_SINGLE_CHARS = 1800


class TranslationAborted(Exception):
    pass


def _sanitize_text(text, max_len=MAX_SINGLE_CHARS):
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _call_baidu_api(q, from_lang, to_lang):
    salt = str(random.randint(32768, 65536))
    sign_str = appid + q + salt + secret_key
    sign = hashlib.md5(sign_str.encode()).hexdigest()

    url = "http://api.fanyi.baidu.com/api/trans/vip/translate"
    params = {
        "q": q,
        "from": from_lang,
        "to": to_lang,
        "appid": appid,
        "salt": salt,
        "sign": sign,
    }
    response = requests.get(url, params=params, timeout=15)
    return response.json()


def _translate_single(sentence, from_lang, to_lang):
    q = _sanitize_text(sentence)
    if not q:
        return sentence

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = _call_baidu_api(q, from_lang, to_lang)
            if "trans_result" in result:
                items = result["trans_result"]
                return " ".join(item["dst"] for item in items)
            elif "error_code" in result:
                error_code = result["error_code"]
                if error_code == "54004":
                    raise TranslationAborted("百度翻译API余额不足，请充值后重试")
                if error_code == "54003":
                    time.sleep(RETRY_DELAY * attempt * 2)
                    continue
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return sentence
            else:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return sentence
        except TranslationAborted:
            raise
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue
            return sentence
        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt * 2)
                continue
            return sentence
        except (ValueError, KeyError):
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue
            return sentence
        except Exception as e:
            print(f"  ❌ 单条翻译异常: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return sentence
    return sentence


def _build_batches(sentences, max_chars=MAX_QUERY_CHARS):
    batches = []
    current_batch = []
    current_len = 0
    for s in sentences:
        s_len = len(s) + 1
        if current_batch and current_len + s_len > max_chars:
            batches.append(current_batch)
            current_batch = []
            current_len = 0
        current_batch.append(s)
        current_len += s_len
    if current_batch:
        batches.append(current_batch)
    return batches


def _translate_batch(sentences, from_lang, to_lang):
    if not sentences:
        return []
    cleaned = [_sanitize_text(s) for s in sentences]
    q = "\n".join(cleaned)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = _call_baidu_api(q, from_lang, to_lang)
            if "trans_result" in result:
                translated = [item["dst"] for item in result["trans_result"]]
                if len(translated) == len(sentences):
                    return translated
                else:
                    return _fallback_individual(cleaned, from_lang, to_lang)
            elif "error_code" in result:
                error_code = result["error_code"]
                if error_code == "54004":
                    raise TranslationAborted("百度翻译API余额不足，请充值后重试")
                if error_code == "54003":
                    time.sleep(RETRY_DELAY * attempt * 2)
                    continue
                if error_code == "54005":
                    return _fallback_individual(cleaned, from_lang, to_lang)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return sentences
            else:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return sentences
        except TranslationAborted:
            raise
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue
            return sentences
        except requests.exceptions.ConnectionError:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt * 2)
                continue
            return sentences
        except (ValueError, KeyError):
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
                continue
            return sentences
        except Exception as e:
            print(f"  ❌ 批量翻译异常: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return sentences
    return sentences


def _fallback_individual(sentences, from_lang, to_lang):
    results = []
    for s in sentences:
        try:
            translated = _translate_single(s, from_lang, to_lang)
            results.append(translated)
        except TranslationAborted:
            raise
        time.sleep(0.3)
    return results


def translate_column(df, src_col, dst_col, output_file, batch_size=BATCH_SIZE, sleep_time=SLEEP_TIME):
    if dst_col not in df.columns:
        df[dst_col] = pd.Series(dtype="object")

    mask = df[dst_col].isna() & df[src_col].notna() & (df[src_col].astype(str).str.strip() != "")
    pending_indices = df.index[mask].tolist()

    if not pending_indices:
        print(f"  ✅ {dst_col} 无需翻译（已全部完成或无源数据）")
        return True

    print(f"  📝 {dst_col}: 待翻译 {len(pending_indices)} 条")

    try:
        raw_texts = [str(df.at[idx, src_col]).strip() for idx in pending_indices]
        sub_batches = _build_batches(raw_texts)

        idx_offset = 0
        for batch_i, sub_batch in enumerate(tqdm(sub_batches, desc=f"  翻译 {dst_col}")):
            translated = _translate_batch(sub_batch, "en", "zh")

            for i, tr in enumerate(translated):
                global_i = idx_offset + i
                if global_i < len(pending_indices):
                    df.at[pending_indices[global_i], dst_col] = str(tr)

            idx_offset += len(sub_batch)

            if batch_i % 10 == 0 and batch_i > 0:
                df.to_csv(output_file, index=False, encoding='utf-8-sig')

            time.sleep(sleep_time)
    except TranslationAborted as e:
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n  🛑 翻译中断: {e}")
        print(f"  💾 已保存当前进度到 {output_file}，充值后重新运行即可续传")
        return False

    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"  ✅ {dst_col} 翻译完成，已保存")
    return True


def translate_asian():
    input_file = r"e:\软工\Asian Art Museum of San Francisco\asian_final.csv"
    output_file = r"e:\软工\Asian Art Museum of San Francisco\asian_final_translated.csv"

    if not os.path.exists(input_file):
        print(f"❌ 找不到 {input_file}")
        return

    df = pd.read_csv(input_file)
    for col in ["title_zh", "type_zh", "material_zh", "description_zh", "artist_zh"]:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
        else:
            df[col] = df[col].astype("object")

    # 从原始CSV提取Artist信息并清洗（去掉国籍和年份）
    orig_file = r"e:\软工\Asian Art Museum of San Francisco\objects_china_verified.csv"
    if os.path.exists(orig_file):
        orig_df = pd.read_csv(orig_file, encoding="gbk")
        obj_artist_map = {}
        for _, r in orig_df.iterrows():
            acc = str(r["Object number"]).strip()
            artist = str(r["Artist"]).strip() if pd.notna(r["Artist"]) else ""
            # 去掉国籍和年份
            artist = re.sub(r"\s*\([^)]*\)", "", artist).strip()
            artist = re.split(
                r"\s+(Chinese|Japanese|Korean|American|Indian|Tibetan|Vietnamese|Thai|Nepalese|Indonesian|Filipino|Malaysian|Cambodian|Myanmar|Burmese|Mongolian|Persian|Iranian|British|French|German|Italian|Dutch|Flemish)\b",
                artist, flags=re.IGNORECASE,
            )[0].strip()
            artist = re.split(r",\s*(\d|born|active|b\.|d\.|ca\.|approx|circa)", artist, flags=re.IGNORECASE)[0].strip()
            artist = artist.rstrip(",").strip()
            obj_artist_map[acc] = artist

        # 填入artist列
        if "artist" not in df.columns:
            df["artist"] = pd.Series(dtype="object")
        for idx, row in df.iterrows():
            acc = str(row.get("accession_number", "")).strip()
            artist = obj_artist_map.get(acc, "")
            df.at[idx, "artist"] = artist
    else:
        print("⚠️ 找不到原始CSV，跳过艺术家翻译")

    if os.path.exists(output_file):
        df_existing = pd.read_csv(output_file)
        if len(df_existing) == len(df):
            # 保留已有翻译进度
            for col in ["title_zh", "type_zh", "material_zh", "description_zh", "artist_zh"]:
                if col in df_existing.columns and col in df.columns:
                    df[col] = df_existing[col]
            print("📄 已加载已有翻译进度，支持断点续传")
        else:
            print("📄 已有翻译文件行数不匹配，重新开始翻译")

    print(f"\n🔄 开始翻译 asian_final (共 {len(df)} 条)")

    translate_tasks = [
        ("title_en", "title_zh"),
        ("type", "type_zh"),
        ("material", "material_zh"),
        ("description", "description_zh"),
        ("artist", "artist_zh"),
    ]

    for src_col, dst_col in translate_tasks:
        if src_col not in df.columns:
            print(f"  ⚠️ 列 {src_col} 不存在，跳过")
            continue
        ok = translate_column(df, src_col, dst_col, output_file)
        if not ok:
            return

    print(f"\n🎉 asian_final 翻译完成！结果保存到：{output_file}")


if __name__ == "__main__":
    translate_asian()
