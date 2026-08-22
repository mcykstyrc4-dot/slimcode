# -*- coding: utf-8 -*-
"""
Собирает секции «Услуги» и «Акции» в index.html из прайса.

Цены лежат в одном месте — в структуре PRICES ниже. Скрипт разворачивает их
в карточки услуг, полный прайс-лист (раскрывающиеся блоки) и карточки акций,
после чего заменяет соответствующие секции в index.html.

Запуск:  python3 tools/make-prices.py
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, 'index.html')


def rub(n):
    """12345 → 12 345 ₽ (неразрывные пробелы, чтобы цена не переносилась)"""
    return '{:,}'.format(n).replace(',', ' ') + ' ₽'


# --- Прайс -----------------------------------------------------------------
# columns — заголовки колонок, rows — (длительность, [цены по колонкам])
PRICES = [
    {
        'slug': 'rsl',
        'name': 'RSL Beautylizer',
        'lead': 'Вакуумно-роликовая проработка с лимфодренажем: моделирует силуэт, '
                'выравнивает рельеф кожи и убирает отёчность.',
        'from': 3600,
        'from_note': 'пробный сеанс 60 минут',
        'durations': ['60 мин', '75 мин', '90 мин'],
        'columns': ['Пробный', 'Разовый', 'От 6 сеансов', 'От 10 сеансов', 'От 15 сеансов'],
        'rows': [
            ('90 минут', [4800, 5800, 5500, 5100, 4800]),
            ('75 минут', [4200, 5200, 4900, 4500, 4200]),
            ('60 минут', [3600, 4700, 4300, 3900, 3600]),
        ],
        'feature': True,
    },
    {
        'slug': 'facelift',
        'name': 'FaceLift Beautylizer',
        'lead': 'Та же технология для лица, шеи и декольте — отдельно или в комплексе '
                'с проработкой тела.',
        'from': 2200,
        'from_note': 'пробный сеанс 30 минут',
        'durations': ['30 мин', 'комплекс с телом'],
        'columns': ['Пробный', 'От 6 сеансов', 'От 10 сеансов', 'От 15 сеансов'],
        'rows': [
            ('30 минут — шея, лицо, декольте', [2200, 2600, 2400, 2200]),
            ('Комплекс 30 + 30 — RSL тело 30 мин и FaceLift 30 мин', [3900, 4600, 4200, 3900]),
            ('Комплекс 60 + 30 — RSL тело 60 мин и FaceLift 30 мин', [5800, 6900, 6300, 5900]),
        ],
    },
    {
        'slug': 'lpg',
        'name': 'LPG-массаж',
        'lead': 'Классика аппаратной коррекции: запускает лимфоток, работает с локальными '
                'жировыми отложениями и «апельсиновой коркой».',
        'from': 2000,
        'from_note': 'пробный сеанс 50 минут',
        'durations': ['50 мин', '60 мин'],
        'columns': ['Пробный', 'Разовый', 'От 6 сеансов', 'От 10 сеансов'],
        'rows': [
            ('50 минут', [2000, 2500, 2200, 2000]),
            ('60 минут', [2300, 2800, 2500, 2300]),
        ],
    },
    {
        'slug': 'mio',
        'name': 'Миостимуляция',
        'lead': 'Импульсная тренировка глубоких мышц: подтягивает живот, бёдра и руки там, '
                'где обычная нагрузка почти не достаёт.',
        'from': 1900,
        'from_note': 'в курсе от 10 сеансов',
        'durations': ['40 мин', '50 мин'],
        'columns': ['Разовый', 'От 10 сеансов'],
        'rows': [
            ('40 минут', [2200, 1900]),
            ('50 минут', [2500, 2200]),
        ],
    },
    {
        'slug': 'presso',
        'name': 'Прессомассаж',
        'lead': 'Мягкая лимфодренажная программа в костюме-прессотерапии: снимает тяжесть '
                'в ногах и отёки уже после первого сеанса.',
        'from': 1200,
        'from_note': 'в курсе от 10 сеансов',
        'durations': ['30 мин', '40 мин'],
        'columns': ['Разовый', 'От 10 сеансов'],
        'rows': [
            ('30 минут', [1500, 1200]),
            ('40 минут', [1800, 1500]),
        ],
    },
    {
        'slug': 'cav',
        'name': 'Кавитация',
        'lead': 'Ультразвук точечно работает с локальными зонами — там, где объёмы не уходят '
                'ни от питания, ни от спорта.',
        'from': 1800,
        'from_note': 'в курсе от 5 сеансов',
        'durations': ['30 мин', '40 мин'],
        'columns': ['Разовый', 'От 5 сеансов'],
        'rows': [
            ('30 минут', [2100, 1800]),
            ('40 минут', [2500, 2200]),
        ],
    },
]

# Курсы: (название, состав, цена, старая цена)
TRIAL_PACKS = [
    ('Пакет S', 'RSL 45 мин + LPG 40 мин + прессомассаж 30 мин', 5500, 8000),
    ('Пакет M', 'RSL 60 мин + LPG 40 мин + прессомассаж 30 мин', 5900, 8400),
    ('Пакет L', 'RSL 60 мин + LPG 50 мин + прессомассаж 30 мин', 6200, 8700),
    ('Пакет XL', 'RSL 75 мин + LPG 50 мин + прессомассаж 30 мин', 6800, 9200),
]
COURSES = [
    ('Express Light', '6 сеансов RSL по 45 мин и 6 LPG по 40 мин', 34800, 39000),
    ('Express', '6 сеансов RSL по 60 мин и 6 LPG по 40 мин', 37200, 41400),
    ('Express+', '6 сеансов RSL по 60 мин и 6 LPG по 50 мин', 39000, 43200),
    ('Express Optima', '6 сеансов RSL по 60 мин и 6 LPG по 60 мин', 40800, 45000),
    ('Express Big', '6 сеансов RSL по 75 мин и 6 LPG по 50 мин', 42600, 46200),
    ('Maxi Light', '10 сеансов RSL по 45 мин и 10 LPG по 40 мин', 52000, 65000),
    ('Maxi', '10 сеансов RSL по 60 мин и 10 LPG по 40 мин', 56000, 69000),
    ('Maxi+', '10 сеансов RSL по 60 мин и 10 LPG по 50 мин', 59000, 72000),
    ('Maxi Optima', '10 сеансов RSL по 60 мин и 10 LPG по 60 мин', 62000, 75000),
    ('Maxi Big', '10 сеансов RSL по 75 мин и 10 LPG по 50 мин', 65000, 77000),
]

# Что показываем в блоке акций — выгодные позиции из курсов
PROMO_PICKS = [
    ('Пакет S', 'Три методики за один визит: RSL, LPG и прессомассаж. Хороший способ познакомиться с курсом.'),
    ('Express Light', 'Шесть сеансов RSL и шесть LPG. Курс, на котором обычно виден первый результат.'),
    ('Maxi Light', 'Десять сеансов RSL и десять LPG. Максимальная выгода за сеанс.'),
]


def services_section():
    cards = []
    for i, s in enumerate(PRICES):
        cls = 'card card--feature' if s.get('feature') else 'card'
        delay = ' data-d="%d"' % min(i, 4) if i else ''
        chips = '\n'.join('          <span class="tag">%s</span>' % d for d in s['durations'])
        head = ('        <div class="card__head">\n'
                '          <p class="card__idx">%02d%s</p>\n'
                '          <h3 class="card__title">%s</h3>\n'
                '        </div>' % (i + 1, ' — ФЛАГМАН' if s.get('feature') else '', s['name']))
        cards.append("""      <article class="%s reveal"%s>
%s
        <p class="card__text">%s</p>
        <p class="card__price">от %s <span>%s</span></p>
        <div class="card__meta">
%s
        </div>
        <button class="btn btn--ghost" data-open-modal data-service="%s">
          Записаться <span class="arw" aria-hidden="true">→</span>
        </button>
      </article>""" % (cls, delay, head, s['lead'], rub(s['from']), s['from_note'], chips, s['name']))

    blocks = []
    for s in PRICES:
        head = '<tr><th>Длительность</th>' + ''.join('<th>%s</th>' % c for c in s['columns']) + '</tr>'
        body = '\n'.join(
            '              <tr><td>%s</td>%s</tr>' % (name, ''.join('<td>%s</td>' % rub(v) for v in vals))
            for name, vals in s['rows'])
        blocks.append("""        <details class="price" id="price-%s">
          <summary>
            <span class="price__name">%s</span>
            <span class="price__from">от %s</span>
          </summary>
          <div class="price__body">
            <div class="ptable-wrap">
              <table class="ptable">
                <thead>%s</thead>
                <tbody>
%s
                </tbody>
              </table>
            </div>
          </div>
        </details>""" % (s['slug'], s['name'], rub(s['from']), head, body))

    def course_rows(items):
        return '\n'.join(
            '              <tr><td><b>%s</b><span class="ptable__note">%s</span></td>'
            '<td>%s</td><td class="ptable__old">%s</td></tr>' % (n, comp, rub(new), rub(old))
            for n, comp, new, old in items)

    blocks.append("""        <details class="price" id="price-courses">
          <summary>
            <span class="price__name">Курсы и пакеты</span>
            <span class="price__from">от %s</span>
          </summary>
          <div class="price__body">
            <div class="ptable-wrap">
              <table class="ptable">
                <caption>Пробные пакеты</caption>
                <thead><tr><th>Пакет</th><th>Цена</th><th>Без пакета</th></tr></thead>
                <tbody>
%s
                </tbody>
              </table>
            </div>
            <div class="ptable-wrap">
              <table class="ptable">
                <caption>Комбинированные курсы</caption>
                <thead><tr><th>Курс</th><th>Цена</th><th>Без курса</th></tr></thead>
                <tbody>
%s
                </tbody>
              </table>
            </div>
          </div>
        </details>""" % (rub(TRIAL_PACKS[0][2]), course_rows(TRIAL_PACKS), course_rows(COURSES)))

    return """<!-- ======================= 3. УСЛУГИ ======================= -->
<section class="section section--light services" id="services">
  <div class="wrap">
    <div class="section-head section-head--split reveal">
      <div>
        <p class="eyebrow">Услуги и цены</p>
        <h2 class="h2">Шесть методик,<br><em>одна программа под вас</em></h2>
      </div>
      <p class="lead">
        На первой встрече специалист оценивает состояние тканей и собирает
        курс из методик, которые работают вместе, а не по отдельности.
      </p>
    </div>

    <div class="cards">

%s

    </div>

    <!-- Полный прайс: раскрывающиеся блоки, чтобы цены были на странице,
         но не перегружали первый экран секции. -->
    <div class="prices reveal" id="prices">
      <h3 class="prices__title">Полный прайс</h3>

%s

      <p class="prices__note">
        Цена за сеанс в курсе зависит от количества сеансов. Курс подбирается
        на консультации — итоговую стоимость назовём после осмотра.
      </p>
    </div>
  </div>
</section>

""" % ('\n\n'.join(cards), '\n\n'.join(blocks))


def promos_section():
    by_name = {n: (comp, new, old) for n, comp, new, old in TRIAL_PACKS + COURSES}
    cards = []
    for i, (name, text) in enumerate(PROMO_PICKS):
        comp, new, old = by_name[name]
        off = round((1 - new / old) * 100)
        delay = ' data-d="%d"' % i if i else ''
        cards.append("""      <article class="promo reveal"%s>
        <span class="promo__badge">−%d%%</span>
        <h3 class="promo__title">%s</h3>
        <p class="promo__text">%s</p>
        <p class="promo__what">%s</p>
        <div class="promo__foot">
          <span class="promo__price">%s</span>
          <span class="promo__old">%s</span>
        </div>
      </article>""" % (delay, off, name, text, comp, rub(new), rub(old)))

    return """<!-- ======================= 4. АКЦИИ ======================= -->
<section class="section section--dark promos" id="promos">
  <div class="wrap">
    <div class="section-head section-head--split reveal">
      <div>
        <p class="eyebrow">Выгодные пакеты</p>
        <h2 class="h2">Курсы <em>дешевле разовых</em></h2>
      </div>
      <p class="lead">Цена указана за весь курс. Полный список пакетов — в прайсе выше.</p>
    </div>

    <div class="cards promos__grid">

%s

    </div>

    <div class="btn-row reveal">
      <button class="btn btn--primary" data-open-modal data-service="Курс процедур">Записаться на курс</button>
      <a class="btn btn--ghost" href="#prices">Смотреть все цены <span class="arw" aria-hidden="true">→</span></a>
    </div>
  </div>
</section>

""" % '\n\n'.join(cards)


def main():
    s = open(PAGE, encoding='utf-8').read()
    start = s.index('<!-- ======================= 3. УСЛУГИ')
    end = s.index('<!-- ======================= 5. ОТЗЫВЫ')
    s = s[:start] + services_section() + promos_section() + s[end:]

    # Список услуг в форме записи держим в тех же названиях, что и в прайсе
    options = '\n'.join('          <option>%s</option>' % p['name'] for p in PRICES)
    s = re.sub(r'(<select id="fService" name="service">\n)(.*?)(\s*</select>)',
               lambda m: m.group(1) + '          <option>Консультация</option>\n' + options +
                         '\n          <option>Курс процедур</option>' + m.group(3),
               s, count=1, flags=re.S)

    open(PAGE, 'w', encoding='utf-8').write(s)
    print('Секции «Услуги» и «Акции» пересобраны.')
    print('Услуг: %d, пробных пакетов: %d, курсов: %d' % (len(PRICES), len(TRIAL_PACKS), len(COURSES)))


if __name__ == '__main__':
    main()
