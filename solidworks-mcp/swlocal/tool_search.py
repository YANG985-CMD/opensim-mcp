"""Search the live tool catalog by name, description and common CAD terms."""
import re

_ALIASES = {
    "装配": "assembly", "配合": "mate", "限位": "limit", "干涉": "interference",
    "间隙": "clearance", "姿态": "pose", "运动": "motion", "关节": "joint",
    "圆角": "fillet", "通孔": "hole", "材料": "material", "质心": "center mass",
    "质量": "mass", "惯量": "inertia", "导出": "export", "导入": "import",
    "工程图": "drawing", "打包": "package", "交付": "delivery", "保存": "save",
    "基线": "baseline", "验证": "verify", "关闭": "close", "尺寸": "dimension",
    "零件": "part", "批量": "batch", "诊断": "audit", "工具": "tool",
    "版本": "compare", "验收": "acceptance", "配方": "recipe", "任务": "task", "重开": "reopen",
    "连接": "connect", "安装": "health", "启动": "connect health",
}


def find_tools(tools, query, limit):
    if not query.strip() or len(query) > 200 or not 1 <= limit <= 20:
        raise ValueError("Use a non-empty query of at most 200 characters and a limit of 1 to 20")
    normalized = query.casefold().strip()
    terms = set(re.findall(r"[a-z0-9]+", normalized)) - {"a", "an", "and", "the", "to", "sw"}
    for alias, keywords in _ALIASES.items():
        if alias in normalized:
            terms.update(keywords.split())
    results = []
    for tool in tools:
        name = tool.name.casefold()
        description = tool.description or ""
        name_terms = set(re.findall(r"[a-z0-9]+", name))
        description_terms = set(re.findall(r"[a-z0-9]+", description.casefold()))
        matched = terms & (name_terms | description_terms)
        if matched or normalized == name:
            rank = (normalized == name, len(matched), len(terms & name_terms))
            result = {"name": tool.name, "summary": description.splitlines()[0][:240] if description else "",
                      "matched_terms": sorted(matched)}
            results.append((rank, result))
    results.sort(key=lambda item: item[1]["name"])
    results.sort(key=lambda item: item[0], reverse=True)
    return [result for _, result in results[:limit]]
