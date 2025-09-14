
# https://chatgpt.com/share/68c63aea-1764-8010-a9c0-f186a2a8acad

import os
import re
from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter, Options
from fontTools.merge import Merger

# -----------------------------
# 配置
# -----------------------------
ascii_prefix = "Inconsolata"      # 英文字体前缀
cjk_prefix = "LXGWBright"         # 中文字体前缀
output_dir = "merged_fonts"
os.makedirs(output_dir, exist_ok=True)

opts = Options()

# -----------------------------
# Step 0: 自动检测字体字重
# -----------------------------
def detect_fonts(prefix):
    """
    在当前目录检测指定前缀的字体文件，返回 {weight_name: filename} 字典
    支持 Regular, Medium, Bold, Italic, BoldItalic 等
    """
    fonts = {}
    for f in os.listdir("."):
        if f.lower().endswith(".ttf") and f.startswith(prefix):
            # 提取字重名称
            name = f[len(prefix):].replace(".ttf","").strip("-_ ").capitalize()
            if not name:
                name = "Regular"
            fonts[name] = f
    return fonts

ascii_fonts = detect_fonts(ascii_prefix)
cjk_fonts = detect_fonts(cjk_prefix)

# 取两者交集，确保每个字重都有对应字体
weights = sorted(set(ascii_fonts.keys()) & set(cjk_fonts.keys()))
print(f"[INFO] 检测到字重: {weights}")

# -----------------------------
# Step 1~5: 批量拼合每个字重
# -----------------------------
for weight_name in weights:
    print(f"\n[INFO] 处理字重: {weight_name}")
    
    ascii_file = ascii_fonts[weight_name]
    cjk_file = cjk_fonts[weight_name]
    
    ascii_subset_file = f"_temp_ascii_{weight_name}.ttf"
    cjk_subset_file = f"_temp_cjk_{weight_name}.ttf"
    merged_file = os.path.join(output_dir, f"Inconsolata-LXGWMono-{weight_name}.ttf")
    
    # Step 1: ASCII 子集
    f_ascii = TTFont(ascii_file)
    ascii_chars = set()
    for t in f_ascii['cmap'].tables:
        ascii_chars.update(t.cmap.keys())
    subsetter = Subsetter(options=opts)
    subsetter.populate(unicodes=ascii_chars)
    subsetter.subset(f_ascii)
    f_ascii.save(ascii_subset_file)
    
    # Step 2: CJK 补集
    f_cjk = TTFont(cjk_file)
    cjk_chars = set()
    for t in f_cjk['cmap'].tables:
        cjk_chars.update(t.cmap.keys())
    cjk_only = cjk_chars - ascii_chars
    subsetter = Subsetter(options=opts)
    subsetter.populate(unicodes=cjk_only)
    subsetter.subset(f_cjk)
    f_cjk.save(cjk_subset_file)
    
    # Step 3: 合并
    merger = Merger()
    merged_font = merger.merge([ascii_subset_file, cjk_subset_file])
    merged_font.save(merged_file)
    
    # Step 4: 修改 name 表
    font = TTFont(merged_file)
    family_name = "Inconsolata-LXGWMono"
    full_name = f"Inconsolata-LXGWMono {weight_name}"
    ps_name = f"InconsolataLXGWMono-{weight_name.replace(' ','')}"
    for record in font['name'].names:
        if record.nameID == 1:
            record.string = family_name.encode(record.getEncoding())
        elif record.nameID == 4:
            record.string = full_name.encode(record.getEncoding())
        elif record.nameID == 6:
            record.string = ps_name.encode(record.getEncoding())
    font.save(merged_file)
    
    # Step 5: 删除临时文件
    os.remove(ascii_subset_file)
    os.remove(cjk_subset_file)
    
    print(f"[OK] 字重 {weight_name} 拼合完成: {merged_file}")

print("\n[INFO] 所有字重拼合完成，可直接安装使用")
