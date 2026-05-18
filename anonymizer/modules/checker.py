import re


DEFAULT_PATTERNS = {
    'date': [r'\\d{4}年\\d{1,2}月\\d{1,2}日', r'\\d{1,2}月\\d{1,2}日', r'\\d{1,2}月'],
    'time': [r'\\d{1,2}:\\d{2}', r'午前\\d{1,2}時', r'午後\\d{1,2}時'],
    'address': [r'.*市.*区.*', r'.*市.*町.*', r'.*区.*町.*'],
    'name': [r'患者[一-龥]{2,3}', r'[一-龥]{2,4}さん'],
}


def find_tokens(text: str, patterns):
    tokens = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            tokens.append((match.group(0), match.span()))
    return tokens
