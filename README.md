# Marketplace API — ДЗ №2

## Стек

- FastAPI + Uvicorn
- PostgreSQL 16
- SQLAlchemy 2.0 (async) + asyncpg
- Flyway (миграции БД)
- JWT (python-jose)
- bcrypt
- datamodel-code-generator (кодогенерация из OpenAPI)
- Docker (multi-stage build)

## Запуск

    docker compose up --build

- API: http://localhost:8001
- Swagger: http://localhost:8001/docs
- БД: localhost:5432 (postgres/postgres, db=marketplace)

## Архитектура

### Кодогенерация
Спецификация в `src/main/resources/openapi/openapi.yaml`. На этапе сборки Docker запускается `datamodel-code-generator`, генерирующий Pydantic v2 модели в `src/app/generated/models.py`. Ручных DTO нет. Файл в `.gitignore`.

### Миграции (Flyway)
SQL-миграции лежат в `src/main/resources/db/migration/`. Контейнер `flyway` в `docker-compose.yml` применяет их до запуска API. API стартует только после успешного завершения миграций.

### Роли
USER, SELLER, ADMIN. SELLER управляет только своими товарами. USER создаёт/отменяет только свои заказы. SELLER не может создавать заказы (403 ACCESS_DENIED).

### Бизнес-логика
- Списание и возврат остатков в транзакции.
- Лимит частоты создания заказа (через user_operations).
- Запрет на второй активный заказ.
- Промокоды (PERCENTAGE, FIXED_AMOUNT) с проверкой срока, лимита, минимальной суммы.
- Снапшот цен в order_items.

### Ошибки и логирование
Единый формат: error_code, message, details. JSON-логи с request_id, user_id, duration_ms, request_body (пароли маскируются). Заголовок X-Request-Id в ответе.

## E2E

### 1. Регистрация

    curl -X POST http://localhost:8001/auth/register -H "Content-Type: application/json" -d '{"email":"seller@test.com","password":"password123","role":"SELLER"}'
    curl -X POST http://localhost:8001/auth/register -H "Content-Type: application/json" -d '{"email":"user@test.com","password":"password123","role":"USER"}'

### 2. Токены

    export SELLER_TOKEN=$(curl -s -X POST http://localhost:8001/auth/login -H "Content-Type: application/json" -d '{"email":"seller@test.com","password":"password123"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
    export USER_TOKEN=$(curl -s -X POST http://localhost:8001/auth/login -H "Content-Type: application/json" -d '{"email":"user@test.com","password":"password123"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

### 3. Создать товар

    curl -X POST http://localhost:8001/products -H "Authorization: Bearer $SELLER_TOKEN" -H "Content-Type: application/json" -d '{"name":"iPhone 15","price":100000,"stock":10,"category":"Electronics"}'

### 4. Создать заказ

    curl -X POST http://localhost:8001/orders -H "Authorization: Bearer $USER_TOKEN" -H "Content-Type: application/json" -d '{"items":[{"product_id":1,"quantity":2}]}'

### 5. Проверка БД

    docker exec -it marketplace-hw2-db-1 psql -U postgres -d marketplace -c "SELECT id, name, stock FROM products; SELECT id, status, total_amount FROM orders;"

### 6. Отмена

    curl -X POST http://localhost:8001/orders/1/cancel -H "Authorization: Bearer $USER_TOKEN"
