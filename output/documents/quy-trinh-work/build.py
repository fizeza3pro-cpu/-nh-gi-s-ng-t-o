from pathlib import Path
from zipfile import ZipFile
from hashlib import sha256
from xml.sax.saxutils import escape
from lxml import etree
import json

ROOT = Path(__file__).resolve().parent
source = ROOT / 'ban-goc.docx'
out = ROOT.parent / 'Quy-trinh-hoan-thien.docx'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
ns = {'w': W}

def p(text, heading=False, diagram=False):
    props = '<w:spacing w:before="120" w:after="100" w:line="278" w:lineRule="auto"/><w:widowControl/>'
    if heading:
        props += '<w:keepNext/><w:keepLines/>'
    if text.endswith(':') and not heading:
        props += '<w:keepNext/>'
    if diagram:
        props += '<w:ind w:left="220"/>'
        if not text.startswith(('Chưa gán được mã', 'Chưa đủ căn cứ')):
            props += '<w:keepNext/><w:keepLines/>'
    if text.startswith('9 Sơ đồ'):
        props += '<w:pageBreakBefore/>'
    bold = '<w:b/>' if heading or text.endswith(':') else ''
    return f'<w:p><w:pPr>{props}</w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>{bold}<w:color w:val="000000"/><w:sz w:val="28"/></w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'

def table(rows):
    count = len(rows[0])
    widths = [3100, 6260] if count == 2 else [3000,3180,3180]
    borders = ''.join(f'<w:{side} w:val="single" w:sz="4" w:color="D9D9D9"/>' for side in ['top','left','bottom','right','insideH','insideV'])
    s = '<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblBorders>'+borders+'</w:tblBorders><w:tblCellMar><w:top w:w="90" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'+''.join(f'<w:gridCol w:w="{x}"/>' for x in widths)+'</w:tblGrid>'
    for i,row in enumerate(rows):
        s += '<w:tr><w:trPr><w:cantSplit/>'+('<w:tblHeader/>' if i==0 else '')+'</w:trPr>'
        for width,text in zip(widths,row):
            s += f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/><w:vAlign w:val="center"/>'+('<w:shd w:fill="E7E6E6"/>' if i==0 else '')+'</w:tcPr>'+p(text,heading=i==0).replace('<w:sz w:val="28"/>','<w:sz w:val="24"/>').replace('<w:keepNext/>','')+'</w:tc>'
        s += '</w:tr>'
    return s+'</w:tbl>'+p('')

lines = (ROOT / 'continuation-v2.md').read_text(encoding='utf-8').splitlines()
parts=[]
i=0
while i < len(lines):
    line=lines[i]
    if line.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].startswith('|'):
            rows.append([x.strip() for x in lines[i].strip('|').split('|')]); i+=1
        parts.append(table(rows)); continue
    if line.strip():
        parts.append(p(line.lstrip('# ').removeprefix('> '),heading=line.startswith('#'),diagram=line.startswith('>')))
    i+=1
with ZipFile(source) as z:
    old=z.read('word/document.xml').decode('utf-8')
    tree=etree.fromstring(old.encode())
    body=tree.find('w:body',ns)
    paragraphs=body.findall('w:p',ns)
    # Giữ nguyên mọi đoạn có chữ; chỉ thay phần dòng trống cuối bằng nội dung tiếp nối.
    import re
    tail=re.search(r'(<w:sectPr\b[\s\S]*?</w:sectPr>)\s*</w:body>',old)
    before=old[:tail.start()]
    # Dùng vị trí từng paragraph trong XML nguyên gốc để không serialize lại phần cũ.
    matches=list(re.finditer(r'<w:p(?:\s[^>]*)?>[\s\S]*?</w:p>',before))
    cutoff=matches[59].start()
    assert not any(''.join(n.itertext()).strip() for n in paragraphs[59:] if n.findall('.//w:t',ns))
    new=before[:cutoff]+''.join(parts)+old[tail.start():]
    with ZipFile(out,'w') as dest:
        for entry in z.infolist():
            dest.writestr(entry,new.encode('utf-8') if entry.filename=='word/document.xml' else z.read(entry.filename))
with ZipFile(source) as a,ZipFile(out) as b:
    changed=[n for n in a.namelist() if a.read(n)!=b.read(n)]
    assert changed==['word/document.xml'], changed
    original=etree.fromstring(a.read('word/document.xml')).find('w:body',ns)
    final=etree.fromstring(b.read('word/document.xml')).find('w:body',ns)
    for j in range(59):
        assert etree.tostring(original[j])==etree.tostring(final[j]), j
(ROOT/'preservation.json').write_text(json.dumps({'source_sha256':sha256(source.read_bytes()).hexdigest(),'changed_parts':changed,'preserved_original_paragraphs':59,'only_removed_empty_trailing_paragraphs':11,'output':str(out)},indent=2),encoding='utf-8')
(ROOT/'artifact.md').write_text('Reference: ban-goc.docx, SHA256 '+sha256(source.read_bytes()).hexdigest()+'\nLetter portrait, margins 2.54 cm, Times New Roman 14 pt. Preserve original written paragraphs 0–58 and all package parts except appended document.xml. Continue after “Các xử lý ở bước này” in Curator. Added headings bold black 14 pt, tables 12 pt. Only empty trailing paragraphs removed. Source file outside workspace not edited.\n',encoding='utf-8')
print(out)
