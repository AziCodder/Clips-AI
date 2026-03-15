# Доступ по IP (без домена)

Если у тебя нет домена и ты используешь публичный IP сервера.

## 1. Замени YOUR_SERVER_IP

В обоих файлах замени `YOUR_SERVER_IP` на публичный IP твоего сервера (например `123.45.67.89`):

- **infra/env/cpu-backend.env**: `TELEGRAM_WEBHOOK_BASE_URL=http://YOUR_SERVER_IP:8001`
- **gpu-worker/.env**: `CPU_API_BASE_URL=http://YOUR_SERVER_IP:8001/api/v1`

## 2. Порты

| Сервис   | Порт | URL                    |
|----------|------|------------------------|
| Фронтенд | 8000 | http://IP:8000         |
| API      | 8001 | http://IP:8001/api/v1  |

## 3. Файрвол

Открой порты 8000 и 8001 для входящих соединений:

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
sudo ufw reload
```

## 4. GPU_IP_ALLOWLIST

В `cpu-backend.env` уже указаны IP GPU-серверов (195.142.145.66, 217.171.200.22). Если добавляешь новый GPU — добавь его IP в список через запятую.

## 5. CORS

`FRONTEND_ORIGIN=*` разрешает запросы с любого origin (в т.ч. по IP). Для ограничения укажи конкретный origin: `http://YOUR_SERVER_IP:8000`.
