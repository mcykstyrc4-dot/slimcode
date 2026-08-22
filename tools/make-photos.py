# -*- coding: utf-8 -*-
"""
Готовит фотографии команды для сайта.

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


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for f in sorted(os.listdir(SRC)):
        if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        name = os.path.splitext(f)[0]
        src = os.path.join(SRC, f)
        img = Image.open(src).convert('RGB').crop(photo_box(src))
        for w in WIDTHS:
            h = round(img.height * w / img.width)
            small = img.resize((w, h), Image.LANCZOS)
            for ext in ('avif', 'webp', 'jpg'):
                out = os.path.join(OUT, '%s-%d.%s' % (name, w, ext))
                fmt = {'jpg': 'JPEG', 'webp': 'WEBP', 'avif': 'AVIF'}[ext]
                params = {'quality': QUALITY[ext]}
                if ext == 'jpg':
                    params.update(optimize=True, progressive=True)
                small.save(out, fmt, **params)
                total += os.path.getsize(out)
        print('%-12s исходник %dx%d → %d вариантов' % (name, img.width, img.height, len(WIDTHS) * 3))

    print('\nВсего в assets/team: %.0f КБ' % (total / 1024))
    for f in sorted(os.listdir(OUT)):
        print('  %-22s %5.1f КБ' % (f, os.path.getsize(os.path.join(OUT, f)) / 1024))


if __name__ == '__main__':
    main()
