from __future__ import annotations

import io
import posixpath
import re
import zipfile
import zlib
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET


TEXT_SUFFIXES = {
    '.txt',
    '.md',
    '.csv',
    '.log',
    '.json',
    '.text',
}
OFFICE_SUFFIXES = {
    '.xlsx',
    '.docx',
    '.pdf',
}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | OFFICE_SUFFIXES

_TEXT_ENCODING_CANDIDATES = (
    'utf-8-sig',
    'utf-8',
    'cp932',
    'shift_jis',
    'euc-jp',
)
_LEGACY_OFFICE_SUFFIXES = {
    '.xls',
    '.doc',
}
_PDF_TEXT_TOKEN_RE = re.compile(r'\((?:\\.|[^\\()])*\)|<([0-9A-Fa-f\s]+)>')
_PDF_SHOW_RE = re.compile(r'(\[(.*?)\]\s*TJ|(\((?:\\.|[^\\()])*\)|<([0-9A-Fa-f\s]+)>)\s*(?:Tj|\'|"))', re.S)
_PDF_STREAM_RE = re.compile(rb'stream\r?\n(.*?)\r?\nendstream', re.S)
_PDF_INVALID_CONTROL_RATIO = 0.02
_PDF_HALFWIDTH_KATAKANA_RATIO = 0.4

_PDF_LITERAL_ESCAPES = {
    'n': b'\n',
    'r': b'\r',
    't': b'\t',
    'b': b'\b',
    'f': b'\f',
    '(': b'(',
    ')': b')',
    '\\': b'\\',
}

_PDF_FILTER_DECODERS = {
    'FlateDecode': zlib.decompress,
}


def extract_uploaded_text(uploaded_file) -> str:
    filename = str(getattr(uploaded_file, 'name', '') or '').strip()
    suffix = Path(filename).suffix.lower()
    raw_bytes = _read_uploaded_bytes(uploaded_file)
    if not raw_bytes:
        return ''

    kind = _detect_upload_kind(filename, raw_bytes)
    if kind == 'plain_text':
        return _extract_plain_text(raw_bytes)
    if kind == 'xlsx':
        return _extract_xlsx_text(raw_bytes)
    if kind == 'docx':
        return _extract_docx_text(raw_bytes)
    if kind == 'pdf':
        return _extract_pdf_text(raw_bytes)

    if suffix in SUPPORTED_SUFFIXES:
        raise ValueError(_unsupported_message_for_suffix(suffix))

    raise ValueError('対応していないファイル形式です。')


def describe_supported_file_types() -> str:
    return '.txt / .md / .csv / .log / .json / .xlsx / .docx / .pdf'


def _read_uploaded_bytes(uploaded_file) -> bytes:
    raw_bytes = uploaded_file.read()
    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(0)
    return raw_bytes or b''


def _detect_upload_kind(filename: str, raw_bytes: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix in _LEGACY_OFFICE_SUFFIXES:
        raise ValueError(_unsupported_message_for_suffix(suffix))

    if suffix in TEXT_SUFFIXES or suffix == '':
        return 'plain_text'

    if suffix == '.pdf' or raw_bytes.startswith(b'%PDF-'):
        return 'pdf'

    if suffix in {'.xlsx', '.docx'} or raw_bytes.startswith(b'PK\x03\x04') or zipfile.is_zipfile(io.BytesIO(raw_bytes)):
        archive_kind = _detect_zip_office_kind(raw_bytes)
        if archive_kind:
            return archive_kind
        raise ValueError(_unsupported_message_for_suffix(suffix))

    if suffix in OFFICE_SUFFIXES:
        raise ValueError(_unsupported_message_for_suffix(suffix))

    if _looks_like_text(raw_bytes):
        return 'plain_text'

    raise ValueError('対応していないファイル形式です。')


def _unsupported_message_for_suffix(suffix: str) -> str:
    if suffix == '.xlsx':
        return 'Excelファイルを読み込めませんでした。.xlsx 形式のファイルを確認してください。'
    if suffix == '.docx':
        return 'Wordファイルを読み込めませんでした。.docx 形式のファイルを確認してください。'
    if suffix == '.pdf':
        return 'PDFファイルを読み込めませんでした。文字情報を含むPDFのみ対応しています。'
    if suffix == '.xls':
        return 'Excelファイルを読み込めませんでした。.xlsx 形式のファイルを使用してください。'
    if suffix == '.doc':
        return 'Wordファイルを読み込めませんでした。.docx 形式のファイルを使用してください。'
    return '対応していないファイル形式です。'


def _looks_like_text(raw_bytes: bytes) -> bool:
    if not raw_bytes or b'\x00' in raw_bytes:
        return False
    sample = raw_bytes[:4096]
    for encoding in _TEXT_ENCODING_CANDIDATES:
        try:
            sample.decode(encoding)
            return True
        except Exception:
            continue
    return False


def _extract_plain_text(raw_bytes: bytes) -> str:
    for encoding in _TEXT_ENCODING_CANDIDATES:
        try:
            return raw_bytes.decode(encoding).replace('\r\n', '\n').replace('\r', '\n').strip()
        except Exception:
            continue
    return raw_bytes.decode('utf-8', errors='ignore').replace('\r\n', '\n').replace('\r', '\n').strip()


def _extract_xlsx_text(raw_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            shared_strings = _read_xlsx_shared_strings(archive)
            sheets = _read_xlsx_sheet_entries(archive)
            blocks: list[str] = []
            for index, (sheet_name, sheet_path) in enumerate(sheets):
                if sheet_path not in archive.namelist():
                    continue
                sheet_text = _extract_xlsx_sheet_text(archive.read(sheet_path), shared_strings)
                if not sheet_text:
                    continue
                if len(sheets) > 1:
                    blocks.append(f'【{sheet_name or f"Sheet{index + 1}"}】\n{sheet_text}')
                else:
                    blocks.append(sheet_text)
            text = '\n\n'.join(blocks).strip()
            if not text:
                raise ValueError('Excelファイルからテキストを抽出できませんでした。')
            return text
    except zipfile.BadZipFile as exc:
        raise ValueError('Excelファイルを読み込めませんでした。.xlsx 形式のファイルを確認してください。') from exc


def _read_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    except KeyError:
        return []

    shared_strings: list[str] = []
    for item in root.findall('.//{*}si'):
        text = ''.join(item.itertext()).strip()
        shared_strings.append(text)
    return shared_strings


def _read_xlsx_sheet_entries(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook_root = ET.fromstring(archive.read('xl/workbook.xml'))
    rels_root = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))

    relationship_map: dict[str, str] = {}
    for rel in rels_root.findall('.//{*}Relationship'):
        rel_id = str(rel.attrib.get('Id') or '').strip()
        target = str(rel.attrib.get('Target') or '').strip()
        if not rel_id or not target:
            continue
        normalized_target = target.lstrip('/')
        if not normalized_target.startswith('xl/'):
            normalized_target = posixpath.normpath(posixpath.join('xl', normalized_target))
        relationship_map[rel_id] = normalized_target

    sheets: list[tuple[str, str]] = []
    for sheet in workbook_root.findall('.//{*}sheets/{*}sheet'):
        sheet_name = str(sheet.attrib.get('name') or '').strip()
        rel_id = str(
            sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            or sheet.attrib.get('r:id')
            or ''
        ).strip()
        sheet_path = relationship_map.get(rel_id)
        if sheet_path:
            sheets.append((sheet_name, sheet_path))
    return sheets


def _extract_xlsx_sheet_text(sheet_bytes: bytes, shared_strings: list[str]) -> str:
    root = ET.fromstring(sheet_bytes)
    rows: list[str] = []
    for row in root.findall('.//{*}sheetData/{*}row'):
        cells: list[str] = []
        for cell in row.findall('{*}c'):
            value = _extract_xlsx_cell_text(cell, shared_strings)
            if value:
                cells.append(value)
        row_text = '\t'.join(cells).strip()
        if row_text:
            rows.append(row_text)
    return '\n'.join(rows).strip()


def _extract_xlsx_cell_text(cell, shared_strings: list[str]) -> str:
    cell_type = str(cell.attrib.get('t') or '').strip()
    value_element = next((child for child in cell if _local_name(child.tag) == 'v'), None)
    inline_string_element = next((child for child in cell if _local_name(child.tag) == 'is'), None)
    formula_value = ''

    if value_element is not None and value_element.text is not None:
        formula_value = value_element.text.strip()

    if cell_type == 's' and formula_value:
        try:
            index = int(formula_value)
            return shared_strings[index] if 0 <= index < len(shared_strings) else formula_value
        except Exception:
            return formula_value
    if cell_type == 'inlineStr' and inline_string_element is not None:
        return ''.join(inline_string_element.itertext()).strip()
    if cell_type == 'b':
        if formula_value in {'1', 'true', 'TRUE'}:
            return 'TRUE'
        if formula_value in {'0', 'false', 'FALSE'}:
            return 'FALSE'
    return formula_value


def _extract_docx_text(raw_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            document_bytes = archive.read('word/document.xml')
            root = ET.fromstring(document_bytes)
            body = next((child for child in root if _local_name(child.tag) == 'body'), None)
            if body is None:
                raise ValueError('Wordファイルから本文を抽出できませんでした。')

            blocks: list[str] = []
            for child in list(body):
                local_name = _local_name(child.tag)
                if local_name == 'p':
                    paragraph_text = _extract_docx_paragraph_text(child)
                    if paragraph_text:
                        blocks.append(paragraph_text)
                elif local_name == 'tbl':
                    table_text = _extract_docx_table_text(child)
                    if table_text:
                        blocks.append(table_text)
            text = '\n\n'.join(blocks).strip()
            if not text:
                raise ValueError('Wordファイルからテキストを抽出できませんでした。')
            return text
    except zipfile.BadZipFile as exc:
        raise ValueError('Wordファイルを読み込めませんでした。.docx 形式のファイルを確認してください。') from exc


def _extract_docx_paragraph_text(paragraph) -> str:
    return ''.join(node.text or '' for node in paragraph.iter() if _local_name(node.tag) == 't').strip()


def _extract_docx_table_text(table) -> str:
    rows: list[str] = []
    for row in list(table):
        if _local_name(row.tag) != 'tr':
            continue
        cells: list[str] = []
        for cell in list(row):
            if _local_name(cell.tag) != 'tc':
                continue
            cell_blocks: list[str] = []
            for child in list(cell):
                child_name = _local_name(child.tag)
                if child_name == 'p':
                    paragraph_text = _extract_docx_paragraph_text(child)
                    if paragraph_text:
                        cell_blocks.append(paragraph_text)
                elif child_name == 'tbl':
                    nested_text = _extract_docx_table_text(child)
                    if nested_text:
                        cell_blocks.append(nested_text)
            cell_text = '\n'.join(cell_blocks).strip()
            if cell_text:
                cells.append(cell_text)
        row_text = '\t'.join(cells).strip()
        if row_text:
            rows.append(row_text)
    return '\n'.join(rows).strip()


def _extract_pdf_text(raw_bytes: bytes) -> str:
    text = _extract_pdf_text_with_library(raw_bytes)
    if text:
        return text
    text = _extract_pdf_text_from_streams(raw_bytes)
    if text:
        return text
    raise ValueError(
        'PDFからテキストを抽出できませんでした。'
        ' 文字情報を含むPDFのみ対応しています。'
        ' 文字化けするPDFや画像のみのPDFは対象外です。'
    )


def _extract_pdf_text_with_library(raw_bytes: bytes) -> str:
    library_candidates = [
        ('pypdf', 'PdfReader'),
        ('PyPDF2', 'PdfReader'),
    ]
    for module_name, class_name in library_candidates:
        try:
            module = __import__(module_name, fromlist=[class_name])
            reader_cls = getattr(module, class_name)
            reader = reader_cls(io.BytesIO(raw_bytes))
            blocks: list[str] = []
            for page in getattr(reader, 'pages', []):
                try:
                    page_text = page.extract_text() or ''
                except Exception:
                    page_text = ''
                page_text = _clean_pdf_text(page_text)
                if page_text:
                    blocks.append(page_text)
            text = '\n\n'.join(blocks).strip()
            if text:
                return text
        except Exception:
            continue
    return ''


def _extract_pdf_text_from_streams(raw_bytes: bytes) -> str:
    blocks: list[str] = []
    for match in _PDF_STREAM_RE.finditer(raw_bytes):
        stream = match.group(1)
        prefix = raw_bytes[max(0, match.start() - 250):match.start()]
        if b'/FlateDecode' in prefix:
            try:
                stream = zlib.decompress(stream)
            except Exception:
                continue
        try:
            content = stream.decode('latin-1', errors='ignore')
        except Exception:
            continue
        text = _clean_pdf_text(_extract_pdf_text_from_content(content))
        if text.strip():
            blocks.append(text.strip())
    return '\n\n'.join(blocks).strip()


def _extract_pdf_text_from_content(content: str) -> str:
    blocks: list[str] = []
    for match in _PDF_SHOW_RE.finditer(content):
        array_content = match.group(2)
        string_token = match.group(3)
        if array_content is not None:
            pieces: list[str] = []
            for token in _PDF_TEXT_TOKEN_RE.finditer(array_content):
                pieces.append(_decode_pdf_text_token(token.group(0)))
            text = ''.join(pieces).strip()
        else:
            text = _decode_pdf_text_token(string_token or '').strip()
        if text:
            blocks.append(text)
    return '\n'.join(blocks).strip()


def _decode_pdf_text_token(token: str) -> str:
    token = str(token or '')
    if not token:
        return ''
    if token.startswith('(') and token.endswith(')'):
        return _clean_pdf_text(_decode_pdf_bytes(_decode_pdf_literal_bytes(token[1:-1])))
    if token.startswith('<') and token.endswith('>'):
        hex_text = re.sub(r'\s+', '', token[1:-1])
        if len(hex_text) % 2 == 1:
            hex_text += '0'
        try:
            data = bytes.fromhex(hex_text)
        except Exception:
            return ''
        return _clean_pdf_text(_decode_pdf_bytes(data))
    return ''


def _decode_pdf_literal_bytes(text: str) -> bytes:
    data = bytearray()
    i = 0
    while i < len(text):
        character = text[i]
        if character != '\\':
            data.append(ord(character))
            i += 1
            continue

        i += 1
        if i >= len(text):
            break
        escape_character = text[i]

        if escape_character in _PDF_LITERAL_ESCAPES:
            data.extend(_PDF_LITERAL_ESCAPES[escape_character])
            i += 1
            continue

        if escape_character in '\n\r':
            if escape_character == '\r' and i + 1 < len(text) and text[i + 1] == '\n':
                i += 1
            i += 1
            continue

        if escape_character.isdigit() and escape_character < '8':
            oct_digits = escape_character
            for _ in range(2):
                if i + 1 < len(text) and text[i + 1].isdigit() and text[i + 1] < '8':
                    i += 1
                    oct_digits += text[i]
                else:
                    break
            try:
                data.append(int(oct_digits, 8))
            except Exception:
                pass
            i += 1
            continue

        data.append(ord(escape_character))
        i += 1
    return bytes(data)


def _decode_pdf_bytes(data: bytes) -> str:
    if not data:
        return ''
    if data.startswith(b'\xfe\xff'):
        try:
            return data[2:].decode('utf-16-be', errors='ignore')
        except Exception:
            return ''
    if data.startswith(b'\xff\xfe'):
        try:
            return data[2:].decode('utf-16-le', errors='ignore')
        except Exception:
            return ''
    for encoding in ('utf-8', 'cp932', 'shift_jis'):
        try:
            return data.decode(encoding)
        except Exception:
            continue
    return data.decode('latin-1', errors='ignore')


def _clean_pdf_text(text: str) -> str:
    normalized = str(text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not normalized:
        return ''
    if not _looks_like_meaningful_pdf_text(normalized):
        return ''
    return normalized


def _looks_like_meaningful_pdf_text(text: str) -> bool:
    visible_chars = [character for character in text if not character.isspace()]
    if not visible_chars:
        return False

    invalid_control_count = sum(
        1
        for character in visible_chars
        if unicodedata.category(character) in {'Cc', 'Cf'}
    )
    if invalid_control_count and invalid_control_count / len(visible_chars) >= _PDF_INVALID_CONTROL_RATIO:
        return False

    halfwidth_katakana_count = sum(
        1
        for character in visible_chars
        if 0xFF61 <= ord(character) <= 0xFF9F
    )
    japanese_count = sum(1 for character in visible_chars if _is_japanese_pdf_character(character))
    if japanese_count == 0:
        return False
    elif (
        halfwidth_katakana_count
        and halfwidth_katakana_count / len(visible_chars) >= _PDF_HALFWIDTH_KATAKANA_RATIO
    ):
        return False

    return True


def _is_japanese_pdf_character(character: str) -> bool:
    codepoint = ord(character)
    if 0x3040 <= codepoint <= 0x30FF:
        return True
    if 0x3400 <= codepoint <= 0x4DBF:
        return True
    if 0x4E00 <= codepoint <= 0x9FFF:
        return True
    if 0xF900 <= codepoint <= 0xFAFF:
        return True
    return False


def _detect_zip_office_kind(raw_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            names = set(archive.namelist())
            if 'word/document.xml' in names:
                return 'docx'
            if 'xl/workbook.xml' in names:
                return 'xlsx'
    except zipfile.BadZipFile:
        return ''
    return ''


def _local_name(tag: str) -> str:
    if '}' in tag:
        return tag.rsplit('}', 1)[1]
    return tag
