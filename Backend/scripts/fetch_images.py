"""
图片采集脚本 — 从 Pexels API 下载食材和菜谱图片到本地静态目录

用法:
    1. 在 https://www.pexels.com/api/ 注册免费账号，获取 API Key
    2. 设置环境变量: set PEXELS_API_KEY=你的key  (或写入 .env)
    3. 运行: python scripts/fetch_images.py

免费额度: 200 请求/小时。首次全量采集约需 2-3 小时分批跑完。
采集后图片保存在 ../../static/images/ 下，映射表写入 ../../static/image_mapping.json

Pexels 条款明确允许下载后使用（只需注明来源），图片 URL 是你的本地路径，永久稳定。
"""
import os
import re
import sys
import json
import time
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PEXELS_URL = "https://api.pexels.com/v1/search"

ROOT = Path(__file__).parent.parent.parent  # FridgeApp/
STATIC = ROOT / "Frontend" / "static"
INGREDIENTS_DIR = STATIC / "images" / "ingredients"
RECIPES_DIR = STATIC / "images" / "recipes"
MAPPING_FILE = STATIC / "image_mapping.json"

# ============ 食材分类（英文 key → 中文名，与前端 EN_TO_ZH 完全一致） ============
CATEGORIES = {
    "水果": {
        "search_suffix": "水果 食材 高清",
        "items": {
            "apple": "苹果", "banana": "香蕉", "blueberry": "蓝莓",
            "grape": "葡萄", "kiwi": "猕猴桃", "lemon": "柠檬",
            "lime": "青柠", "mango": "芒果", "orange": "橙子",
            "peach": "桃子", "pear": "梨", "pineapple": "菠萝",
            "strawberry": "草莓", "watermelon": "西瓜",
        },
    },
    "蔬菜": {
        "search_suffix": "蔬菜 食材 高清",
        "items": {
            "bell_pepper": "彩椒", "cabbage": "卷心菜", "carrot": "胡萝卜",
            "cauliflower": "花椰菜", "chilli_pepper": "辣椒", "corn": "玉米",
            "cucumber": "黄瓜", "eggplant": "茄子", "garlic": "大蒜",
            "ginger": "生姜", "green_beans": "四季豆", "leek": "韭菜",
            "lettuce": "生菜", "mushroom": "蘑菇", "onion": "洋葱",
            "potato": "土豆", "spinach": "菠菜",
            "sweet potato": "红薯", "sweetpotato": "红薯",
            "tomato": "番茄", "green leaves": "绿叶菜",
        },
    },
    "肉蛋生鲜类": {
        "search_suffix": "食材 高清",
        "items": {
            "chicken": "鸡肉", "egg": "鸡蛋", "meat": "肉类",
            "shrimp": "虾",
        },
    },
    "饮料乳品类": {
        "search_suffix": "饮品 食材 高清",
        "items": {
            "milk": "牛奶", "yogurt": "酸奶", "cheese": "奶酪",
            "cola": "可乐", "water": "水", "fanta": "芬达",
            "sprite": "雪碧", "drink": "饮料",
        },
    },
    "包装食品类": {
        "search_suffix": "食品 包装 高清",
        "items": {
            "bread": "面包", "chocolate": "巧克力",
        },
    },
}


def collect_all_ingredients() -> dict:
    """展开所有食材为 { en_key: zh_name } 映射"""
    result = {}
    for cat_name, cat_data in CATEGORIES.items():
        for en_key, zh_name in cat_data["items"].items():
            result[en_key] = zh_name
    return result


def collect_recipe_names(data_dir: Path) -> list:
    """从 HowToCook 数据中提取所有菜名"""
    names = []
    for md_file in data_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("# ") and not line.startswith("## "):
                    name = line[2:].strip()
                    name = re.sub(r'^#+\s*', '', name)
                    name = re.sub(r'\s*(的)?(做法|制作方法|家常做法|食谱|配方|菜谱)\s*$', '', name)
                    name = re.sub(r'\s*(（[^）]*）)\s*$', '', name)
                    name = re.sub(r'\s*(\([^)]*\))\s*$', '', name)
                    if 2 <= len(name) <= 20:
                        names.append(name)
                    break
        except Exception:
            pass
    return list(set(names))


def slugify(text: str) -> str:
    """中文名 / 英文名 → 文件名"""
    text = re.sub(r'[^\w一-鿿]', '_', text)
    return text.strip("_")[:40]


def search_image(query: str, orientation: str = "landscape") -> Optional[str]:
    """搜索图片，返回 Pexels 下载 URL"""
    if not PEXELS_API_KEY:
        return None
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": query,
        "per_page": 3,
        "orientation": orientation,
        "locale": "zh-CN",
    }
    try:
        resp = requests.get(PEXELS_URL, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            logger.warning("  API error %d: %s", resp.status_code, resp.text[:120])
            return None
        photos = resp.json().get("photos", [])
        if photos:
            return photos[0]["src"]["large"]
        return None
    except Exception as e:
        logger.warning("  搜索异常: %s", e)
        return None


def find_local_image(target_dir: Path, slug_name: str) -> Optional[str]:
    """在本地目录中查找已有图片缓存"""
    if not target_dir.exists():
        return None
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        candidate = target_dir / f"{slug_name}{ext}"
        if candidate.exists():
            return f"/static/images/{target_dir.parent.name}/{target_dir.name}/{candidate.name}"
    for f in target_dir.iterdir():
        if f.is_file() and f.stem == slug_name:
            return f"/static/images/{target_dir.parent.name}/{target_dir.name}/{f.name}"
    return None


def download_image(url: str, save_path: Path) -> bool:
    """下载图片到本地静态目录"""
    if save_path.exists():
        logger.info("  已存在，跳过: %s", save_path.name)
        return True
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "FridgeApp/1.0"})
        if resp.status_code == 200:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(resp.content)
            logger.info("  下载成功: %s (%.0fKB)", save_path.name, len(resp.content) / 1024)
            return True
    except Exception as e:
        logger.warning("  下载失败: %s", e)
    return False


def fetch_all(data_dir: Path, dry_run: bool = False):
    """主流程"""
    existing = {}
    if MAPPING_FILE.exists():
        existing = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))

    mapping = existing.copy()
    mapping.setdefault("ingredients", {})

    all_ingredients = collect_all_ingredients()

    # === 按分类采集食材图片 ===
    for cat_name, cat_data in CATEGORIES.items():
        items = cat_data["items"]
        logger.info("===== %s (%d 种) =====", cat_name, len(items))

        for en_key, zh_name in items.items():
            map_key = en_key

            # 1. 映射表已有记录
            if map_key in mapping["ingredients"] and mapping["ingredients"][map_key]:
                logger.info("OK %s (%s) (映射已有)", zh_name, en_key)
                continue

            # 2. 检查中文名旧映射（兼容旧版）
            old_key = zh_name
            if old_key in mapping["ingredients"] and mapping["ingredients"][old_key]:
                mapping["ingredients"][map_key] = mapping["ingredients"][old_key]
                logger.info("OK %s (%s) (迁移旧映射)", zh_name, en_key)
                if old_key != map_key and old_key in mapping["ingredients"]:
                    del mapping["ingredients"][old_key]
                continue

            # 3. 检查本地图片缓存
            local_path = find_local_image(INGREDIENTS_DIR, slugify(zh_name))
            if not local_path:
                local_path = find_local_image(INGREDIENTS_DIR, slugify(en_key))
            if local_path:
                mapping["ingredients"][map_key] = local_path
                logger.info("OK %s (%s) (本地缓存 -> %s)", zh_name, en_key, local_path)
                continue

            # 4. 调用 Pexels API
            search_query = "{} {}".format(zh_name, cat_data["search_suffix"])
            logger.info("搜索: %s (%s)", zh_name, search_query)
            url = search_image(search_query, "square")
            if not url:
                mapping["ingredients"][map_key] = ""
                logger.info("  未找到")
                continue

            ext = Path(urlparse(url).path).suffix or ".jpg"
            filename = "{}{}".format(slugify(zh_name), ext)
            save_path = INGREDIENTS_DIR / filename

            if not dry_run:
                if download_image(url, save_path):
                    mapping["ingredients"][map_key] = "/static/images/ingredients/{}".format(filename)
                else:
                    mapping["ingredients"][map_key] = ""
            time.sleep(1.2)

    # === 菜谱 ===
    mapping.setdefault("recipes", {})
    recipe_names = collect_recipe_names(data_dir)
    logger.info("===== 菜谱 (%d 道) =====", len(recipe_names))
    for name in recipe_names:
        if name in mapping["recipes"] and mapping["recipes"][name]:
            logger.info("OK %s (映射已有)", name)
            continue

        local_path = find_local_image(RECIPES_DIR, slugify(name))
        if local_path:
            mapping["recipes"][name] = local_path
            logger.info("OK %s (本地缓存 -> %s)", name, local_path)
            continue

        logger.info("搜索: %s", name)
        url = search_image("{} 菜".format(name), "landscape")
        if not url:
            mapping["recipes"][name] = ""
            logger.info("  未找到")
            continue

        ext = Path(urlparse(url).path).suffix or ".jpg"
        filename = "{}{}".format(slugify(name), ext)
        save_path = RECIPES_DIR / filename

        if not dry_run:
            if download_image(url, save_path):
                mapping["recipes"][name] = "/static/images/recipes/{}".format(filename)
            else:
                mapping["recipes"][name] = ""
        time.sleep(1.2)

    # === 写入映射表 ===
    if not dry_run:
        MAPPING_FILE.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info("映射表已写入: %s", MAPPING_FILE)
        logger.info("  食材: %d 项", len(mapping["ingredients"]))
        logger.info("  菜谱: %d 项", len(mapping["recipes"]))

    return mapping


if __name__ == "__main__":
    data_path = ROOT / "Frontend" / "data" / "dishes"
    if not data_path.exists():
        print("数据目录不存在: {}".format(data_path))
        sys.exit(1)

    if not PEXELS_API_KEY:
        print("=" * 60)
        print("请先设置 PEXELS_API_KEY 环境变量")
        print("  1. 访问 https://www.pexels.com/api/ 注册免费账号")
        print("  2. 获取 API Key")
        print("  3. 运行: set PEXELS_API_KEY=你的key")
        print("=" * 60)
        print()
        print("将以 dry_run 模式运行（仅预览，不下载）...")
        fetch_all(data_path, dry_run=True)
    else:
        fetch_all(data_path)
