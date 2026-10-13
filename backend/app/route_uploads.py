"""Read local Excel/CSV stop tables without evaluating formulas or fetching links."""
import base64
import csv
import io
import posixpath
import re
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile
from fastapi import HTTPException

NAME={'waypoint','wegpunkt','wegpunt','name','stop','stopp','station','ladestation'}
LAT={'latitude','lat','breitengrad','breedtegraad'}
LON={'longitude','lon','lng','längengrad','lengtegraad'}
LINK={'url','link','maps','google maps','googlemaps','karte'}
CHARGE={'charge duration','charging time','ladedauer','laadduur'}
COORD=re.compile(r'^\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*$')
CHARGER=re.compile(r'\b(supercharger|charging(?:station)?|charger|ionity|fastned|enbw|allego|aral\s+pulse|ladestation|ladehalt|ladesäule|ladepunkt)\b',re.I)


def xml(data):
    if re.search(br'<!\s*(DOCTYPE|ENTITY)',data.replace(b'\0',b''),re.I):raise ValueError()
    return ET.fromstring(data)


def station_url(value):
    """Only explicit target coordinates, never a viewport center or geocoding."""
    url=urlparse(value)
    if url.scheme!='https' or not re.fullmatch(r'(?:www\.|maps\.)?google\.(?:com|de|nl|at)',url.hostname or ''):return None
    query=parse_qs(url.query)
    target=next((query[key][0] for key in ('query','q','destination','daddr') if key in query),'')
    match=COORD.fullmatch(target)
    if not match and url.path.startswith('/maps/place/'):
        match=re.search(r'!3d([-+]?\d+(?:\.\d+)?)!4d([-+]?\d+(?:\.\d+)?)',url.path)
    if not match:
        match=COORD.fullmatch(unquote(url.path.removeprefix('/maps/place/')).rstrip('/')) if url.path.startswith('/maps/place/') else None
    if not match:return None
    place=next((query[key][0] for key in ('query_place_id','destination_place_id') if key in query),None)
    return float(match[1]),float(match[2]),place


def excel_rows(content):
    raw=base64.b64decode(content,validate=True)
    if len(raw)>500_000:raise ValueError()
    with ZipFile(io.BytesIO(raw)) as archive:
        info=archive.infolist()
        if any(item.compress_type not in (0,8) or item.flag_bits&1 for item in info) or len(info)>100 or sum(item.file_size for item in info)>8_000_000 or any(item.file_size>2_000_000 for item in info):raise ValueError()
        def read(path):return xml(archive.read(path))
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared=[''.join(node.itertext()) for node in read('xl/sharedStrings.xml').findall('s:si',ns)]
        if len(shared)>10000:raise ValueError()
        sheets=read('xl/workbook.xml').findall('s:sheets/s:sheet',ns)
        if len(sheets)!=1:raise HTTPException(422,'Bitte genau eine Routentabelle in der Excel-Datei verwenden.')
        relationships={node.attrib['Id']:node.attrib['Target'] for node in read('xl/_rels/workbook.xml.rels')}
        rid=sheets[0].attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        target=relationships[rid]
        path=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        root=read(path)
        relpath=posixpath.dirname(path)+'/_rels/'+posixpath.basename(path)+'.rels'
        links={node.attrib['Id']:node.attrib['Target'] for node in read(relpath)} if relpath in archive.namelist() else {}
        hyperlinks={node.attrib['ref']:links.get(node.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'), '') for node in root.findall('s:hyperlinks/s:hyperlink',ns)}
        rows=[]
        for row in root.findall('s:sheetData/s:row',ns):
            cells={}
            for cell in row.findall('s:c',ns):
                reference=cell.attrib['r'];column=re.sub(r'\d','',reference)
                value=cell.findtext('s:v','',ns)
                if cell.attrib.get('t')=='s':value=shared[int(value)]
                elif cell.attrib.get('t')=='inlineStr':value=''.join(cell.find('s:is',ns).itertext())
                link=hyperlinks.get(reference,'')
                formula=cell.findtext('s:f','',ns)
                match=re.fullmatch(r'HYPERLINK\("([^"]+)"\s*[,;]\s*"([^"]*)"\)',formula,re.I)
                if match:link=match[1];value=value or match[2]
                cells[column]=(str(value).strip(),link)
            rows.append(cells)
            if len(rows)>200:raise ValueError()
        return rows


def table_plan(upload):
    try:
        if upload.filename.lower().endswith('.xlsx'):
            if upload.encoding!='base64':raise ValueError()
            rows=excel_rows(upload.content)
        else:
            if upload.encoding!='text' or len(upload.content.encode())>500_000:raise ValueError()
            try:dialect=csv.Sniffer().sniff(upload.content[:4096],delimiters=',;\t')
            except csv.Error:dialect=csv.excel
            rows=[{str(i):(value.strip(),'') for i,value in enumerate(row)} for row in csv.reader(io.StringIO(upload.content),dialect)]
            if len(rows)>200:raise ValueError()
        for index,row in enumerate(rows[:20]):
            headers={column:value[0].casefold().strip() for column,value in row.items()}
            name=next((column for column,value in headers.items() if value in NAME),None)
            if name is not None:break
        else:raise HTTPException(422,'Die Tabelle benötigt eine Spalte Wegpunkt/Name und Stationskoordinaten oder Google-Maps-Links.')
        def field(row,options):return next((row.get(column,('',''))[0] for column,value in headers.items() if value in options),'')
        stops=[]
        for row in rows[index+1:]:
            label=row.get(name,('',''))[0]
            if not label:continue
            lat,lon=field(row,LAT),field(row,LON)
            point=next((station_url(value) for text,link in row.values() for value in (link,text) if value and station_url(value)),None)
            if lat and lon:point=(float(lat.replace(',','.')),float(lon.replace(',','.')),point[2] if point else None)
            if not point:raise HTTPException(422,'Für einen Tabellenstopp fehlen eindeutige Stationskoordinaten. Breitengrad und Längengrad ergänzen; Namen werden nicht automatisch geocodiert.')
            duration=field(row,CHARGE)
            charging=bool(CHARGER.search(label)) or any(float(number)>0 for number in re.findall(r'\d+(?:\.\d+)?',duration))
            stops.append({'name':label,'latitude':point[0],'longitude':point[1],'kind':'charging' if charging else 'waypoint',
                          'operator':field(row,{'operator','betreiber','exploitant'}),'address':field(row,{'address','adresse','adres'}),'google_place_id':point[2] or field(row,{'google_place_id','google places id'}) or None})
        if not stops or len(stops)>50:raise ValueError()
        if stops[-1]['kind']=='waypoint':stops[-1]['kind']='destination'
        return {'title':upload.filename.rsplit('.',1)[0][:200],'stops':stops}
    except HTTPException:raise
    except (ValueError,KeyError,IndexError,TypeError,AttributeError,BadZipFile,ET.ParseError,RecursionError,csv.Error):
        raise HTTPException(422,'Die Routentabelle ist ungültig oder zu groß. Bitte einen Plan mit benannten Stopps und Koordinaten verwenden.') from None
