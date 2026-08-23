<?php
/**
 * Slim Code Lab — приём заявок с сайта и отправка их в Telegram.
 *
 * Зачем нужен этот файл: токен бота нельзя держать в коде страницы —
 * его увидит любой посетитель. Страница шлёт заявку сюда, а уже этот
 * скрипт (на вашем сервере) обращается к API Telegram.
 *
 * КАК ПОДКЛЮЧИТЬ
 *  1. Создайте бота у @BotFather, получите токен вида 123456789:AA...
 *  2. Узнайте id чата, куда слать заявки:
 *     — напишите боту любое сообщение (или добавьте его в группу),
 *     — откройте https://api.telegram.org/bot<ТОКЕН>/getUpdates
 *     — возьмите значение result[0].message.chat.id
 *  3. Пропишите токен и chat_id ниже или, что надёжнее, задайте их
 *     переменными окружения TG_BOT_TOKEN и TG_CHAT_ID.
 *  4. Положите файл на хостинг, например в /api/lead.php
 *  5. В index.html укажите этот адрес: CONFIG.endpoint = '/api/lead.php'
 *
 * Требуется PHP 7.4+ (есть запасной путь, если расширение cURL не включено).
 */
declare(strict_types=1);

// --- Настройки -------------------------------------------------------------
$BOT_TOKEN = getenv('TG_BOT_TOKEN') ?: '';   // ЗАМЕНИТЬ или задать в окружении
$CHAT_ID   = getenv('TG_CHAT_ID')   ?: '';   // ЗАМЕНИТЬ или задать в окружении
$THROTTLE_SECONDS = 15;                      // не чаще одной заявки с IP
$MAX_BODY = 4096;                            // ограничение размера запроса

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

function fail(int $code, string $message): void {
    http_response_code($code);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_UNICODE);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    fail(405, 'Метод не поддерживается');
}
if ($BOT_TOKEN === '' || $CHAT_ID === '') {
    fail(500, 'Не заданы TG_BOT_TOKEN и TG_CHAT_ID');
}

// --- Простая защита от потока заявок с одного адреса ------------------------
$ip = $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
$stamp = sys_get_temp_dir() . '/scl-lead-' . md5($ip);
if (is_file($stamp) && (time() - (int) filemtime($stamp)) < $THROTTLE_SECONDS) {
    fail(429, 'Слишком часто, попробуйте через несколько секунд');
}
@touch($stamp);

// --- Разбор и проверка данных ----------------------------------------------
$raw = (string) file_get_contents('php://input', false, null, 0, $MAX_BODY + 1);
if (strlen($raw) > $MAX_BODY) fail(413, 'Слишком большой запрос');

$data = json_decode($raw, true);
if (!is_array($data)) fail(400, 'Некорректный JSON');

/** Обрезаем, чистим управляющие символы и ограничиваем длину */
function clean($value, int $limit): string {
    $s = is_scalar($value) ? (string) $value : '';
    $s = preg_replace('/[\x00-\x1F\x7F]+/u', ' ', $s) ?? '';
    $s = trim(preg_replace('/\s{2,}/u', ' ', $s) ?? '');
    return mb_substr($s, 0, $limit);
}

// Скрытое поле-ловушка: у человека оно всегда пустое
if (clean($data['company'] ?? '', 50) !== '') {
    echo json_encode(['ok' => true], JSON_UNESCAPED_UNICODE);   // боту отвечаем «успех»
    exit;
}

$name    = clean($data['name'] ?? '', 60);
$phone   = clean($data['phone'] ?? '', 25);
$service = clean($data['service'] ?? '', 60);
$salon   = clean($data['salon'] ?? '', 60);
$page    = clean($data['page'] ?? '', 200);

$digits = preg_replace('/\D/', '', $phone) ?? '';
if (mb_strlen($name) < 2)     fail(422, 'Не указано имя');
if (strlen($digits) !== 11)   fail(422, 'Некорректный номер телефона');

/** Читаемый вид номера: 79001234567 → +7 (900) 123-45-67 */
function prettyPhone(string $d): string {
    return strlen($d) === 11
        ? sprintf('+7 (%s) %s-%s-%s',
            substr($d, 1, 3), substr($d, 4, 3), substr($d, 7, 2), substr($d, 9, 2))
        : '+' . $d;
}

// --- Текст сообщения собираем на сервере ------------------------------------
// Намеренно не используем текст, присланный страницей: иначе через форму
// можно было бы отправить в ваш чат произвольное содержимое.
$message = "🔔 Новая заявка с сайта\n\n"
    . "Имя: {$name}\n"
    . "Телефон: " . prettyPhone($digits) . "\n"
    . "Услуга: " . ($service !== '' ? $service : '—') . "\n"
    . "Салон: " . ($salon !== '' ? $salon : '—') . "\n\n"
    . "Страница: " . ($page !== '' ? $page : '—') . "\n"
    . "Время: " . date('d.m.Y H:i');

$payload = json_encode([
    'chat_id' => $CHAT_ID,
    'text'    => $message,                  // без parse_mode: текст уходит как есть
    'disable_web_page_preview' => true,
], JSON_UNESCAPED_UNICODE);

$url = "https://api.telegram.org/bot{$BOT_TOKEN}/sendMessage";
$response = false;

if (function_exists('curl_init')) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $payload,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
    ]);
    $response = curl_exec($ch);
    $status = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    curl_close($ch);
} else {
    // Запасной путь, если cURL не установлен
    $ctx = stream_context_create(['http' => [
        'method'        => 'POST',
        'header'        => "Content-Type: application/json\r\n",
        'content'       => $payload,
        'timeout'       => 10,
        'ignore_errors' => true,
    ]]);
    $response = @file_get_contents($url, false, $ctx);
    $status = 0;
    if (isset($http_response_header[0]) &&
        preg_match('/\s(\d{3})\s/', $http_response_header[0], $m)) {
        $status = (int) $m[1];
    }
}

if ($response === false || $status !== 200) {
    error_log('Telegram sendMessage failed: ' . var_export($response, true));
    fail(502, 'Не удалось отправить сообщение');
}

echo json_encode(['ok' => true], JSON_UNESCAPED_UNICODE);
