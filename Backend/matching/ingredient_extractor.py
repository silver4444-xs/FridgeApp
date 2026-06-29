"""
食材提取器 — 从 HowToCook Markdown 菜谱中提取结构化食材信息
"""
import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

TOOL_KEYWORDS = [
    '刀', '锅', '砧板', '保鲜膜', '厨房纸', '厨房纸巾', '筷子', '蒸锅',
    '微波炉', '烤箱', '榨汁机', '破壁机', '滤网', '牙签', '保鲜袋',
    '碗', '盘子', '碟子', '勺子', '铲子', '擀面杖', '漏勺', '打蛋器',
    '电子秤', '温度计', '刮刀', '模具', '油纸', '锡纸', '烤盘',
    '密封袋', '裱花袋', '料理机', '搅拌机', '高压锅', '砂锅',
]


def _clean_ingredient_name(raw: str) -> str:
    raw = re.sub(r'!\[.*?\]\(.*?\)', '', raw)
    raw = re.sub(r'（[^）]*(?:害怕|同学|欢迎|可选|根据|建议|按|参考|注意|喜欢|讨厌|可加|可不|自行|适量|酌情|选配)[^）]*）', '', raw)
    raw = re.sub(r'\([^)]*(?:optional|or|adjust|to taste)[^)]*\)', '', raw, flags=re.IGNORECASE)
    # 移除括号中的用量描述 (如 "鸡肉(200g)" → "鸡肉")
    raw = re.sub(r'[（(]\s*\d+\s*[a-zA-Z]*[）)]', '', raw)
    # 移除 " - 描述" 后缀 (新格式中的补充说明)
    raw = re.sub(r'\s*[-–—]\s*[^-–—]+$', '', raw)
    raw = re.sub(r'^[\d\s\.\、]+', '', raw)
    raw = re.sub(r'\s*(适量|少许|若干|一些|几个|数个)\s*$', '', raw)
    return raw.strip()


def _split_aliases(name: str) -> List[str]:
    aliases = [name]
    m = re.search(r'[（(]\s*(?:或者|或)\s*([^）)]+)[）)]', name)
    if m:
        main = re.sub(r'[（(]\s*(?:或者|或)\s*[^）)]+[）)]', '', name).strip()
        alt = m.group(1).strip()
        aliases = [main, alt]
    return aliases


class IngredientExtractor:

    @staticmethod
    def extract(markdown_content: str) -> Dict:
        result = {"ingredients": [], "steps": [], "tips": "", "time": ""}

        ing_section = (
            _extract_section(markdown_content, r'##\s*必备原料和工具')
            or _extract_section(markdown_content, r'##\s*所需食材')
        )
        if ing_section:
            result["ingredients"] = IngredientExtractor._parse_ingredients(ing_section)

        op_section = (
            _extract_section(markdown_content, r'##\s*操作')
            or _extract_section(markdown_content, r'##\s*制作步骤')
        )
        if op_section:
            result["steps"] = IngredientExtractor._parse_steps(op_section)

        tips_section = (
            _extract_section(markdown_content, r'##\s*附加内容')
            or _extract_section(markdown_content, r'##\s*标签')
        )
        if tips_section:
            result["tips"] = tips_section.strip()

        result["time"] = IngredientExtractor._estimate_time(markdown_content)
        return result

    @staticmethod
    def _parse_ingredients(section: str) -> List[Dict]:
        ingredients = []
        current_required = True

        for line in section.split('\n'):
            stripped = line.strip()

            if stripped.startswith('###'):
                sub = stripped.replace('#', '').strip()
                current_required = not ('可选' in sub or '选配' in sub)
                continue

            # 支持旧格式 "- item" 或 "* item"，以及新格式 "N. item"
            m = re.match(r'^[-*]\s+(.+)', stripped)
            if not m:
                m = re.match(r'^\d+\.\s+(.+)', stripped)
            if not m:
                continue

            raw = m.group(1).strip()
            if not raw or re.match(r'^!\[', raw):
                continue

            if any(t in raw for t in TOOL_KEYWORDS):
                continue

            cleaned = _clean_ingredient_name(raw)
            if not cleaned or len(cleaned) < 1:
                continue

            names = _split_aliases(cleaned)
            ingredients.append({
                "name": names[0],
                "aliases": names[1:] if len(names) > 1 else [],
                "required": current_required,
            })

        return ingredients

    @staticmethod
    def _parse_steps(section: str) -> List[str]:
        steps = []
        lines = section.split('\n')
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()

            # 新格式: "### 第N步" 开头的步骤块
            if re.match(r'^###\s*第\d+步', stripped):
                desc_parts = []
                i += 1
                while i < len(lines):
                    sub = lines[i].strip()
                    if re.match(r'^###\s*第\d+步', sub):
                        break
                    if sub.startswith('描述:'):
                        desc_parts.append(sub.replace('描述:', '').strip())
                    elif sub.startswith('步骤:'):
                        desc_parts.append(sub.replace('步骤:', '').strip())
                    elif sub and not sub.startswith('方法:') and not sub.startswith('工具:') and not sub.startswith('时间:'):
                        desc_parts.append(sub)
                    i += 1
                step_text = ' '.join(desc_parts) if desc_parts else stripped
                if step_text:
                    steps.append(step_text)
                continue

            # 旧格式: "- step description"
            if not stripped or stripped.startswith('!['):
                i += 1
                continue
            m = re.match(r'^[-*]\s+(.+)', stripped)
            if m:
                step = re.sub(r'!\[.*?\]\(.*?\)', '', m.group(1)).strip()
                if step:
                    steps.append(step)
            i += 1
        return steps

    @staticmethod
    def _estimate_time(content: str) -> str:
        if '★★★★★' in content: return '90分钟'
        if '★★★★' in content: return '60分钟'
        if '★★★' in content: return '30分钟'
        if '★★' in content: return '20分钟'
        if '★' in content: return '10分钟'
        return '未知'


def _extract_section(content: str, header_pattern: str) -> Optional[str]:
    lines = content.split('\n')
    start = -1
    header_level = 0

    for i, line in enumerate(lines):
        m = re.match(header_pattern, line.strip())
        if m:
            start = i
            h = re.match(r'^(#+)\s', line.strip())
            header_level = len(h.group(1)) if h else 2
            break

    if start == -1:
        return None

    body_lines = []
    for i in range(start + 1, len(lines)):
        line = lines[i]
        h = re.match(r'^(#+)\s', line.strip())
        if h and len(h.group(1)) <= header_level:
            break
        body_lines.append(line)

    return '\n'.join(body_lines)
