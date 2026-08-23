# -*- coding: utf-8 -*-
"""
Скачивает шрифты Google Fonts к себе в assets/fonts и собирает локальный CSS.

Зачем: при подключении шрифтов ссылкой каждый посетитель на каждой странице
обращается к серверам Google — туда уходит его IP-адрес. Это передача данных
за пределы страны, которую пришлось бы описывать в политике. Со своими файлами
такого обращения нет, и страница грузится на один внешний запрос меньше.

Берём только те начертания, что реально используются, и подмножества символов
кириллицы и латиницы: греческий и вьетнамский на сайте не нужны.

Запуск:  python3 tools/fetch-fonts.py
"""
import os, re, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'assets', 'fonts')
CSS = os.path.join(OUT, 'fonts.css')
UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
URL = ('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800'
       '&family=Cormorant+Garamond:wght@400;500;600&display=swap')
KEEP = ('cyrillic', 'cyrillic-ext', 'latin', 'latin-ext')


def get(url, binary=False):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    data = urllib.request.urlopen(req, timeout=60).read()
    return data if binary else data.decode('utf-8')


def main():
    os.makedirs(OUT, exist_ok=True)
    css = get(URL)
    blocks = re.findall(r'/\* (\S+) \*/\n(@font-face \{.*?\})', css, re.S)
    out, total, saved = [], 0, 0

    for subset, block in blocks:
        if subset not in KEEP:
            continue
        family = re.search(r"font-family: '([^']+)'", block).group(1)
        weight = re.search(r'font-weight: (\d+)', block).group(1)
        url = re.search(r'url\((https://[^)]+)\)', block).group(1)
        name = '%s-%s-%s.woff2' % (family.split()[0].lower(), weight, subset)
        path = os.path.join(OUT, name)
        if not os.path.isfile(path):
            open(path, 'wb').write(get(url, binary=True))
        total += os.path.getsize(path)
        saved += 1
        out.append(re.sub(r'url\(https://[^)]+\)', "url('%s')" % name, block)
                   .replace('@font-face {', '/* %s */\n@font-face {' % subset))

    open(CSS, 'w', encoding='utf-8').write(
        '/* Шрифты лежат рядом с сайтом: к сторонним серверам страница не обращается.\n'
        '   Файл собран tools/fetch-fonts.py, руками не правится. */\n\n'
        + '\n\n'.join(out) + '\n')
    print('начертаний: %d, файлов: %d, всего %.0f КБ' % (saved, saved, total / 1024))


if __name__ == '__main__':
    main()
