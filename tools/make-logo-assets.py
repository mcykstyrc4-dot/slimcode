# -*- coding: utf-8 -*-
"""
Собирает все файлы логотипа Slim Code Lab из присланного макета.

Исходник — assets/source/logo-original.jpg: белая графика на фирменной
красной плашке. Скрипт отделяет графику от фона по альфа-каналу (не обтравкой
по контуру, а расчётом прозрачности из цвета — поэтому тонкие линии остаются
целыми, а по краям нет красной каймы) и раскладывает на рабочие варианты.

Запуск:  python3 tools/make-logo-assets.py
Нужны:   pillow, numpy

Настройка насыщенности надписи — константа BOLD ниже. Знак (силуэт и эллипс)
не утолщается никогда: это рисунок, а не шрифт.
"""
import os
import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'assets', 'source', 'logo-original.jpg')
OUT = os.path.join(ROOT, 'assets')

# Насколько плотнее делать надпись «Slim Code»:
#   1 — как в исходнике, 3 — лёгкое (+19%), 5 — среднее (+37%), 7 — заметное (+55%)
BOLD = 5
BOLD_TAGLINE = 3          # подпись мельче, ей хватает меньшего наращивания

BRAND = (150, 31, 23)     # #961F17 — фирменный красный с плашки
TEXT_X = 236              # правее — надпись, левее — знак
TAG_Y = 125               # ниже этой строки в правой части — подпись-слоган
UP = 4                    # утолщаем на увеличении, чтобы край остался гладким


def alpha_from_plate(path):
    """Прозрачность белой графики поверх сплошной плашки."""
    im = np.asarray(Image.open(path).convert('RGB')).astype(np.float32)
    corners = np.concatenate([im[0:6, 0:6].reshape(-1, 3), im[0:6, -6:].reshape(-1, 3),
                              im[-6:, 0:6].reshape(-1, 3), im[-6:, -6:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    # p = a*255 + (1-a)*bg  →  a = (p - bg)/(255 - bg).
    # Считаем по зелёному и синему: там контраст с красным фоном максимальный.
    num = (im[:, :, 1] - bg[1]) + (im[:, :, 2] - bg[2])
    a = np.clip(num / ((255 - bg[1]) + (255 - bg[2])), 0, 1)
    a[a < 0.06] = 0       # шум JPEG вокруг контуров
    a[a > 0.94] = 1
    return a


def embolden(region, kernel):
    """Наращивает штрих: увеличиваем, расширяем максимум-фильтром, уменьшаем обратно."""
    if kernel <= 1:
        return region
    h, w = region.shape
    img = Image.fromarray((region * 255).round().astype(np.uint8), 'L')
    img = img.resize((w * UP, h * UP), Image.LANCZOS).filter(ImageFilter.MaxFilter(kernel))
    img = img.resize((w, h), Image.LANCZOS)
    return np.asarray(img).astype(np.float32) / 255


def layer(alpha, rgb):
    """Обрезает по содержимому и красит в нужный цвет."""
    ys, xs = np.nonzero(alpha)
    crop = alpha[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2] = rgb
    out[:, :, 3] = (crop * 255).round().astype(np.uint8)
    return Image.fromarray(out, 'RGBA')


def icon(mark, size, pad_ratio=0.16):
    m = layer(mark, (255, 255, 255))
    box = int(size * (1 - 2 * pad_ratio))
    scale = min(box / m.width, box / m.height)
    m = m.resize((max(1, round(m.width * scale)), max(1, round(m.height * scale))), Image.LANCZOS)
    canvas = Image.new('RGBA', (size, size), BRAND + (255,))
    canvas.alpha_composite(m, ((size - m.width) // 2, (size - m.height) // 2))
    return canvas


def main():
    a = alpha_from_plate(SRC)
    a[:TAG_Y, TEXT_X:] = embolden(a[:TAG_Y, TEXT_X:], BOLD)
    a[TAG_Y:, TEXT_X:] = embolden(a[TAG_Y:, TEXT_X:], BOLD_TAGLINE)
    a = np.clip(a, 0, 1)

    compact = a.copy()
    compact[TAG_Y:, TEXT_X + 4:] = 0        # в шапке слоган не нужен: на 32-38 px он нечитаем
    mark = np.zeros_like(a)
    mark[:, :235] = a[:, :235]

    layer(a, (255, 255, 255)).save(os.path.join(OUT, 'logo-full.png'), optimize=True)
    layer(compact, (255, 255, 255)).save(os.path.join(OUT, 'logo.png'), optimize=True)
    layer(compact, BRAND).save(os.path.join(OUT, 'logo-dark.png'), optimize=True)
    layer(mark, (255, 255, 255)).save(os.path.join(OUT, 'logo-mark.png'), optimize=True)
    icon(mark, 32).save(os.path.join(OUT, 'favicon-32.png'), optimize=True)
    icon(mark, 180).save(os.path.join(OUT, 'apple-touch-icon.png'), optimize=True)

    og = Image.new('RGBA', (1200, 630), BRAND + (255,))
    full = layer(a, (255, 255, 255))
    full = full.resize((820, round(full.height * 820 / full.width)), Image.LANCZOS)
    og.alpha_composite(full, ((1200 - full.width) // 2, (630 - full.height) // 2 - 20))
    og.convert('RGB').save(os.path.join(OUT, 'og-cover.jpg'), quality=92, optimize=True)

    for f in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, f)
        if os.path.isfile(p):
            print('%-24s %-9s %5.1f КБ' % (f, '%dx%d' % Image.open(p).size, os.path.getsize(p) / 1024))


if __name__ == '__main__':
    main()
