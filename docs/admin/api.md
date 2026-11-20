# HTTP API

Все эндпоинты начинаются с `/api`. Интерактивное описание (Swagger) доступно по адресу `/api/docs` в локальном режиме и при включённом `DEMO_MODE`.

В облачном режиме запросы выполняются с токеном доступа в заголовке `Authorization: Bearer <токен>`, который выдаёт вход (`POST /api/auth/login`). Токен обновляется через `POST /api/auth/refresh` по `httpOnly`-cookie.

## Служебные

| Метод и адрес | Назначение |
|---|---|
| `GET /api/health` | Состояние сервиса (`200` или `503`, если база данных недоступна) |
| `GET /api/config` | Режим работы, включена ли авторизация, доступные возможности |

## Авторизация

| Метод и адрес | Назначение |
|---|---|
| `POST /api/auth/register` | Регистрация |
| `POST /api/auth/login` | Вход |
| `POST /api/auth/refresh` | Обновление токена доступа |
| `POST /api/auth/logout` | Выход |
| `POST /api/auth/verify-email`, `resend-verification` | Подтверждение почты |
| `POST /api/auth/forgot-password`, `reset-password` | Сброс пароля |

## Профиль

| Метод и адрес | Назначение |
|---|---|
| `GET`, `PATCH`, `DELETE /api/me` | Профиль: чтение, изменение, удаление аккаунта |
| `POST /api/me/password` | Смена пароля |
| `GET`, `PUT /api/me/settings` | Пользовательские настройки |

## Сценарии и запуски

| Метод и адрес | Назначение |
|---|---|
| `POST`, `GET /api/workflows/` | Создать сценарий, получить список |
| `GET`, `PUT`, `DELETE /api/workflows/{id}` | Получить, обновить, удалить сценарий |
| `POST /api/workflows/{id}/activate`, `deactivate` | Включить и выключить сценарий |
| `POST /api/workflows/bulk-delete` | Удалить несколько сценариев |
| `POST /api/workflows/{id}/execute` | Выполнить и дождаться результата |
| `POST /api/workflows/{id}/execute-async` | Запустить в фоне |
| `GET /api/executions/{id}/progress` | Ход выполнения (по шагам) |
| `POST /api/executions/{id}/cancel` | Остановить запуск |
| `GET /api/executions`, `GET /api/executions/{id}` | История и подробности запуска |
| `POST /api/executions/bulk-delete` | Удалить записи истории |
| `POST /api/workflows/test-node` | Проверить один шаг на тестовых данных |
| `GET /api/templates`, `POST /api/workflows/from-template/{id}` | Шаблоны и создание сценария из шаблона |
| `GET /api/workflows/{id}/webhook-url` | Ссылка вызова сценария |

## ИИ-помощник

| Метод и адрес | Назначение |
|---|---|
| `GET /api/ai/models` | Доступные модели |
| `POST /api/ai/chat` | Сообщение помощнику. В ответе текст и, при необходимости, готовый граф |

## Подключения

| Метод и адрес | Назначение |
|---|---|
| `GET`, `POST /api/connections` | Список и создание подключений |
| `DELETE /api/connections/{id}` | Удаление |
| `GET /api/connections/email-presets` | Готовые настройки почтовых сервисов |
| `GET /api/oauth/status`, `/api/oauth/start`, `/api/oauth/{family}/callback` | Вход через аккаунт Google, Яндекс, Mail.ru |

## Тарифы и оплата

| Метод и адрес | Назначение |
|---|---|
| `GET /api/plans` | Тарифы |
| `GET /api/billing/subscription` | Текущая подписка |
| `POST /api/billing/quote` | Расчёт стоимости (в том числе смены тарифа) |
| `POST /api/billing/checkout` | Создание платежа |
| `POST /api/billing/cancel` | Отмена подписки |
| `GET /api/billing/payments` | История платежей |
| `POST /api/billing/yookassa/webhook` | Уведомления ЮKassa |

## Telegram и ссылки вызова

| Метод и адрес | Назначение |
|---|---|
| `POST /api/telegram/webhook/{connection_id}` | Приём сообщений от Telegram |
| `GET /api/telegram/status`, `POST /api/telegram/sync` | Состояние и синхронизация |
| `POST /api/webhooks/{workflow_id}/{подпись}` | Запуск сценария внешней системой |

## Администрирование

Требуют роль администратора.

| Метод и адрес | Назначение |
|---|---|
| `GET /api/admin/stats` | Общая статистика |
| `GET`, `PATCH /api/admin/users`, `/api/admin/users/{id}` | Пользователи |
| `POST /api/admin/users/{id}/grant` | Выдать подписку |
| `GET`, `PUT /api/admin/plans`, `/api/admin/plans/{code}` | Тарифы |
| `GET /api/admin/payments` | Платежи |
| `GET`, `PUT /api/admin/settings` | Глобальные настройки |
| `GET /api/admin/audit` | Журнал действий |

## Ошибки

Ошибки возвращаются с HTTP-статусом и телом вида:

```json
{"detail": {"code": "quota_exceeded", "message": "Исчерпан лимит запусков с нейросетью"}}
```

Частые коды: `401` — нет или просрочен токен; `403` — недостаточно прав; `404` — не найдено; `429` — слишком много запросов или исчерпан лимит; `503` — сервис временно недоступен (например, нейросеть).
