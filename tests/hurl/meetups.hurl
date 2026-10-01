# Сквозной сценарий MeetupBoard: организатор публикует митап, участник регистрируется и задаёт вопрос.
# Запуск: hurl --test --variable host=http://localhost:8000 --variable run=$(date +%s) tests/hurl/*.hurl

# Регистрация организатора
POST {{host}}/api/users
Content-Type: application/json
{
  "user": {
    "email": "org{{run}}@example.com",
    "username": "org{{run}}",
    "password": "password123"
  }
}
HTTP 201
[Captures]
org_token: jsonpath "$.user.token"
[Asserts]
jsonpath "$.user.username" == "org{{run}}"
jsonpath "$.user.token" isString


# Регистрация участника
POST {{host}}/api/users
Content-Type: application/json
{
  "user": {
    "email": "guest{{run}}@example.com",
    "username": "guest{{run}}",
    "password": "password123"
  }
}
HTTP 201
[Captures]
guest_token: jsonpath "$.user.token"


# Повторная регистрация с тем же email в другом регистре — конфликт
POST {{host}}/api/users
Content-Type: application/json
{
  "user": {
    "email": "ORG{{run}}@example.com",
    "username": "someone{{run}}",
    "password": "password123"
  }
}
HTTP 409
[Asserts]
jsonpath "$.errors.email[0]" == "уже занято"


# Организатор публикует митап на 1 место
POST {{host}}/api/events
Authorization: Token {{org_token}}
Content-Type: application/json
{
  "event": {
    "title": "Hurl-митап {{run}}",
    "description": "Тестирование API как код",
    "body": "Разбираем Hurl на реальном сервисе",
    "startsAt": "2031-03-14T19:00:00+03:00",
    "city": "Москва",
    "capacity": 1,
    "tagList": ["Testing", "hurl"]
  }
}
HTTP 201
[Captures]
slug: jsonpath "$.event.slug"
[Asserts]
jsonpath "$.event.tagList" count == 2
jsonpath "$.event.seatsLeft" == 1
jsonpath "$.event.attending" == false


# Мероприятие видно в списке ближайших
GET {{host}}/api/events?upcoming=true&organizer=org{{run}}
HTTP 200
[Asserts]
jsonpath "$.eventsCount" == 1
jsonpath "$.events[0].slug" == "{{slug}}"


# Участник занимает единственное место (префикс Bearer тоже поддерживается)
POST {{host}}/api/events/{{slug}}/attend
Authorization: Bearer {{guest_token}}
HTTP 200
[Asserts]
jsonpath "$.event.attending" == true
jsonpath "$.event.seatsLeft" == 0


# Организатору места уже не хватает
POST {{host}}/api/events/{{slug}}/attend
Authorization: Token {{org_token}}
HTTP 409
[Asserts]
jsonpath "$.errors.event[0]" == "свободных мест нет"


# Участник задаёт вопрос в обсуждении
POST {{host}}/api/events/{{slug}}/comments
Authorization: Token {{guest_token}}
Content-Type: application/json
{
  "comment": {"body": "Будет ли запись?"}
}
HTTP 201
[Captures]
comment_id: jsonpath "$.comment.id"


# Организатор модерирует обсуждение и удаляет вопрос
DELETE {{host}}/api/events/{{slug}}/comments/{{comment_id}}
Authorization: Token {{org_token}}
HTTP 204


# Посторонний не может удалить мероприятие
DELETE {{host}}/api/events/{{slug}}
Authorization: Token {{guest_token}}
HTTP 403


# Без токена создать мероприятие нельзя
POST {{host}}/api/events
Content-Type: application/json
{
  "event": {"title": "x", "description": "x", "body": "x", "startsAt": "2031-03-14T19:00:00+03:00"}
}
HTTP 401
[Asserts]
jsonpath "$.errors.token[0]" == "отсутствует"


# Организатор удаляет мероприятие
DELETE {{host}}/api/events/{{slug}}
Authorization: Token {{org_token}}
HTTP 204


GET {{host}}/api/events/{{slug}}
HTTP 404
