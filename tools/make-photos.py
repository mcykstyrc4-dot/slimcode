# -*- coding: utf-8 -*-
"""
Готовит фотографии для сайта: команду и первый экран.

Исходники — карточки из соцсетей в assets/source/team/: фотография на фирменной
красной плашке с подписью внизу. Скрипт находит саму фотографию (плашка и
подпись отбрасываются), обрезает её и раскладывает в три формата и два размера:

    assets/team/<имя>-320.avif / .webp / .jpg
    assets/team/<имя>-640.avif / .webp / .jpg

AVIF и WebP отдаются современным браузерам, JPEG остаётся запасным вариантом.
Разметка использует <picture> с srcset, браузер сам выбирает формат и размер.

Запуск:  python3 tools/make-photos.py
Нужны:   pillow, numpy
"""
import os
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'assets', 'source', 'team')
OUT = os.path.join(ROOT, 'assets', 'team')

WIDTHS = [320, 640]           # карточка занимает максимум ~280 CSS-пикселей
HERO_WIDTHS = [480, 960]      # блок первого экрана — примерно 460 CSS-пикселей
HERO_RATIO = 3 / 2            # горизонтальный кадр: обрезаем снимок минимально
HERO_FOCUS = 0.5              # кадр по центру: аппарат и мастер и так в середине
QUALITY = {'avif': 55, 'webp': 78, 'jpg': 82}


def photo_box(path):
    """Границы фотографии внутри карточки: плашка и подпись отбрасываются."""
    im = np.asarray(Image.open(path).convert('RGB')).astype(np.int16)
    edge = np.concatenate([im[0:5, :].reshape(-1, 3), im[:, 0:5].reshape(-1, 3)])
    bg = np.median(edge, axis=0)
    notbg = np.abs(im - bg).sum(axis=2) > 60
    # Строки фотографии заняты почти на всю ширину; строки подписи — нет
    rows = np.nonzero(notbg.mean(axis=1) > 0.6)[0]
    y0, y1 = rows.min(), rows.max()
    cols = np.nonzero(notbg[y0:y1 + 1].mean(axis=0) > 0.6)[0]
    return int(cols.min()), int(y0), int(cols.max()) + 1, int(y1) + 1


def save_variants(img, prefix, widths):
    total = 0
    # Апскейл запрещён: вариант шире исходника выглядит мыльным
    widths = [w for w in widths if w <= img.width] or [img.width]
    for w in widths:
        h = round(img.height * w / img.width)
        small = img.resize((w, h), Image.LANCZOS)
        for ext in ('avif', 'webp', 'jpg'):
            out = '%s-%d.%s' % (prefix, w, ext)
            fmt = {'jpg': 'JPEG', 'webp': 'WEBP', 'avif': 'AVIF'}[ext]
            params = {'quality': QUALITY[ext]}
            if ext == 'jpg':
                params.update(optimize=True, progressive=True)
            small.save(out, fmt, **params)
            total += os.path.getsize(out)
    return total


def make_hero():
    """Кадр для первого экрана: обрезаем горизонтальный снимок под вертикальный блок."""
    src = os.path.join(ROOT, 'assets', 'source', 'hero.jpg')
    if not os.path.isfile(src):
        return 0
    img = Image.open(src).convert('RGB')
    w, h = img.size
    if w / h > HERO_RATIO:
        nw, nh = round(h * HERO_RATIO), h
    else:
        nw, nh = w, round(w / HERO_RATIO)
    x = round((w - nw) * HERO_FOCUS)
    y = round((h - nh) * 0.5)
    img = img.crop((x, y, x + nw, y + nh))
    print('%-12s кадр %dx%d → %d вариантов' % ('hero', img.width, img.height, len(HERO_WIDTHS) * 3))
    return save_variants(img, os.path.join(os.path.dirname(OUT), 'hero'), HERO_WIDTHS)


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for f in sorted(os.listdir(SRC)):
        if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        name = os.path.splitext(f)[0]
        src = os.path.join(SRC, f)
        img = Image.open(src).convert('RGB').crop(photo_box(src))
        total += save_variants(img, os.path.join(OUT, name), WIDTHS)
        print('%-12s исходник %dx%d → %d вариантов' % (name, img.width, img.height, len(WIDTHS) * 3))

    total += make_hero()
    print('\nВсего фотографий: %.0f КБ' % (total / 1024))
    for f in sorted(os.listdir(OUT)):
        print('  %-22s %5.1f КБ' % (f, os.path.getsize(os.path.join(OUT, f)) / 1024))


if __name__ == '__main__':
    main()
