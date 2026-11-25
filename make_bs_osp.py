import re, os
SRC = r'D:/Modding/MO2/mods/Baka Haeun UNP（BHUNP）/CalienteTools/BodySlide/SliderSets/BHUNP 3BBB Advanced Legacy.osp'
OUT = 'work/out/bsbody/CalienteTools/BodySlide/SliderSets/YunDao Tiantian Body.osp'
s = open(SRC, encoding='utf-8-sig', errors='replace').read()
s = s.replace('name="BHUNP 3BBB Advanced Ver 2"', 'name="YunDao Tiantian Body"', 1)
s = re.sub(r'<SourceFile>[^<]*</SourceFile>', '<SourceFile>YunDao Tiantian Body.nif</SourceFile>', s, count=1)
s = re.sub(r'<OutputPath>[^<]*</OutputPath>', r'<OutputPath>CalienteTools\\Preview</OutputPath>', s, count=1)
s = re.sub(r'<OutputFile([^>]*)>[^<]*</OutputFile>', r'<OutputFile\1>YunDao Tiantian Body</OutputFile>', s, count=1)
s = s.replace('</SliderSet>', '        <Shape target="hair">hair</Shape>\n    </SliderSet>', 1)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, 'w', encoding='utf-8-sig', newline='\r\n').write(s)
print('wrote', OUT, len(s))
import xml.etree.ElementTree as ET
t = ET.parse(OUT); root = t.getroot()
sete = root.find('SliderSet')
print('set name', sete.get('name'))
for tag in ('DataFolder','SourceFile','OutputPath','OutputFile'):
    print(tag, sete.find(tag).text, sete.find(tag).attrib)
print('shapes', len(sete.findall('Shape')), 'sliders', len(sete.findall('Slider')))
print('last shape', sete.findall('Shape')[-1].attrib, sete.findall('Shape')[-1].text)
