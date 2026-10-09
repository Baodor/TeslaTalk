import ast
import json
import re
from pathlib import Path


def test_frontend_translation_catalog_covers_literals_and_preserves_placeholders():
    source=Path(__file__).resolve().parents[2]/'frontend'/'src'
    catalog=json.loads((source/'translations.json').read_text())
    for key,translations in catalog.items():
        assert set(translations)=={'en','nl','de-AT'},key
        placeholders=sorted(re.findall(r'\{\w+\}',key))
        for language,text in translations.items():
            assert text.strip(),(key,language)
            assert sorted(re.findall(r'\{\w+\}',text))==placeholders,(key,language)
    for path in [*source.glob('*.ts'),*source.glob('*.tsx')]:
        for match in re.finditer(r"\bt\(\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')",path.read_text()):
            key=re.sub(r'\s+',' ',ast.literal_eval(match[1])).strip()
            assert key in catalog,(path.name,key)
