/**
 * Slim Code Lab — приём заявок с сайта и отправка их в Telegram.
 * Вариант для Cloudflare Workers (бесплатного тарифа хватает с запасом).
 *
 * Зачем нужен: токен бота нельзя держать в коде страницы — его увидит любой
 * посетитель. Страница шлёт заявку сюда, воркер обращается к API Telegram.
 *
 * КАК ПОДКЛЮЧИТЬ
 *  1. Создайте бота у @BotFather и получите токен.
 *  2. Узнайте id чата: напишите боту, откройте
 *     https://api.telegram.org/bot<ТОКЕН>/getUpdates и возьмите
 *     result[0].message.chat.id
 *  3. Создайте воркер и положите туда этот файл:
 *       npx wrangler init slimcode-lead
 *       npx wrangler deploy
 *  4. Задайте секреты (они не попадут в код):
 *       npx wrangler secret put TG_BOT_TOKEN
 *       npx wrangler secret put TG_CHAT_ID
 *  5. В переменной ALLOWED_ORIGINS ниже укажите свой домен.
 *  6. В index.html пропишите адрес воркера:
 *       CONFIG.endpoint = 'https://slimcode-lead.<ваш>.workers.dev'
 */

// ЗАМЕНИТЬ: домены, с которых разрешено принимать заявки
const ALLOWED_ORIGINS = [
  'https://slimcodelab.ru',
  'https://www.slimcodelab.ru',
];

const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' };

function corsHeaders(origin) {
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allowed,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

function reply(status, body, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...JSON_HEADERS, ...corsHeaders(origin) },
  });
}

// Обрезаем управляющие символы и ограничиваем длину
function clean(value, limit) {
  if (typeof value !== 'string') return '';
  return value
    .replace(/[\u0000-\u001F\u007F]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
    .slice(0, limit);
}

// Читаемый вид номера: 79001234567 → +7 (900) 123-45-67
function prettyPhone(d) {
  return d.length === 11
    ? `+7 (${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9, 11)}`
    : '+' + d;
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (request.method !== 'POST') {
      return reply(405, { ok: false, error: 'Метод не поддерживается' }, origin);
    }
    if (!env.TG_BOT_TOKEN || !env.TG_CHAT_ID) {
      return reply(500, { ok: false, error: 'Не заданы секреты TG_BOT_TOKEN и TG_CHAT_ID' }, origin);
    }
    // Заявки принимаем только со своего сайта
    if (origin && !ALLOWED_ORIGINS.includes(origin)) {
      return reply(403, { ok: false, error: 'Источник не разрешён' }, origin);
    }

    let data;
    try {
      data = await request.json();
    } catch (e) {
      return reply(400, { ok: false, error: 'Некорректный JSON' }, origin);
    }

    // Скрытое поле-ловушка: у человека оно всегда пустое
    if (clean(data.company, 50) !== '') return reply(200, { ok: true }, origin);

    const name = clean(data.name, 60);
    const phone = clean(data.phone, 25);
    const service = clean(data.service, 60) || '—';
    const salon = clean(data.salon, 60) || '—';
    const page = clean(data.page, 200) || '—';
    const digits = phone.replace(/\D/g, '');

    if (name.length < 2) return reply(422, { ok: false, error: 'Не указано имя' }, origin);
    if (digits.length !== 11) return reply(422, { ok: false, error: 'Некорректный номер телефона' }, origin);

    // Текст собираем здесь, а не берём присланный страницей: иначе через форму
    // можно было бы отправить в чат произвольное содержимое.
    const text = [
      '🔔 Новая заявка с сайта',
      '',
      'Имя: ' + name,
      'Телефон: ' + prettyPhone(digits),
      'Услуга: ' + service,
      'Салон: ' + salon,
      '',
      'Страница: ' + page,
      'Время: ' + new Date().toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }),
    ].join('\n');

    const tg = await fetch('https://api.telegram.org/bot' + env.TG_BOT_TOKEN + '/sendMessage', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({
        chat_id: env.TG_CHAT_ID,
        text,                          // без parse_mode: текст уходит как есть
        disable_web_page_preview: true,
      }),
    });

    if (!tg.ok) {
      console.error('Telegram sendMessage failed:', tg.status, await tg.text());
      return reply(502, { ok: false, error: 'Не удалось отправить сообщение' }, origin);
    }
    return reply(200, { ok: true }, origin);
  },
};
