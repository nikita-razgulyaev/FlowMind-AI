"""Форма обратной связи: приём, ловушка для ботов (и отсутствие ложных срабатываний), копия в Formspree, админка, контакты."""
import csv
import io
import itertools
import uuid

import pytest

from app.config import settings
from app.services import ratelimit
from tests.conftest import TEST_MODE, register, run

cloud_only = pytest.mark.skipif(TEST_MODE != "cloud", reason="cloud only")

_n = itertools.count(1)


def mark() -> str:
    """Уникальная метка в тексте — чтобы находить свои обращения среди чужих (база общая на весь прогон)."""
    return f"метка{next(_n)}x{uuid.uuid4().hex[:6]}"


def payload(**over) -> dict:
    body = {"type": "question", "message": f"Не получается подключить Telegram-бота {mark()}", "name": "Иван", "email": "ivan@example.com",
            "page": "/connections", "client_id": uuid.uuid4().hex, "hp": "", "elapsed_ms": 8000}
    body.update(over)
    return body


def send(client, headers=None, **over):
    return client.post("/api/feedback", json=payload(**over), headers=headers or {})


def find(admin, text, status=""):
    r = admin.get("/admin/feedback", params={"q": text, "status": status, "limit": 100})
    assert r.status_code == 200, r.text
    return r.json()["items"]


@pytest.fixture
def relaxed(monkeypatch):
    """Для тестов, которые шлют много обращений подряд: убираем лимит в минуту."""
    monkeypatch.setattr(ratelimit.feedback_burst_limiter, "limit", 10_000)
    monkeypatch.setattr(ratelimit.feedback_hour_limiter, "limit", 10_000)


# ───────────────────────── приём ─────────────────────────

@cloud_only
def test_guest_feedback_is_stored_and_forwarded(client, admin, fake_net):
    m = mark()
    r = send(client, message=f"Хочу интеграцию с Битрикс24 {m}", type="idea")
    assert r.status_code == 200 and r.json() == {"ok": True}
    [item] = find(admin, m)
    assert (item["status"], item["type"], item["email"], item["name"], item["page"]) == ("new", "idea", "ivan@example.com", "Иван", "/connections")
    assert item["user_id"] is None and item["spam_reason"] == "" and item["forward_status"] == "sent"

    [call] = fake_net.formspree_calls
    assert call["url"] == "https://formspree.io/f/testform"
    body = call["body"]
    assert body["message"] == f"Хочу интеграцию с Битрикс24 {m}" and body["email"] == "ivan@example.com"
    assert body["_subject"].startswith("FlowMind AI · Идея:") and body["account"] == "гость"
    assert "hp" not in body and "elapsed_ms" not in body and "client_id" not in body      # служебные поля наружу не уходят
    assert call["headers"]["accept"] == "application/json"


@cloud_only
def test_logged_in_user_is_linked_and_prefilled(client, admin, fake_net):
    s = register(client)
    m = mark()
    r = client.post("/api/feedback", json=payload(message=f"Не проходит оплата {m}", email="", name="", type="payment"), headers=s.headers)
    assert r.status_code == 200
    [item] = find(admin, m)
    assert item["email"] == s.email and item["user_id"] is not None and item["plan"] == "free" and item["type"] == "payment"
    assert fake_net.formspree_calls[-1]["body"]["account"].endswith("тариф free")


@cloud_only
def test_stale_token_does_not_block_feedback(client, admin):
    """Просроченная сессия не должна лишать человека возможности пожаловаться — он просто считается гостем."""
    m = mark()
    r = send(client, headers={"Authorization": "Bearer not.a.real.token"}, message=f"Меня выкинуло из аккаунта {m}")
    assert r.status_code == 200
    assert find(admin, m)[0]["user_id"] is None


@cloud_only
def test_page_query_and_hash_are_dropped(client, admin):
    """В адресе страницы бывают токены (сброс пароля, подтверждение email) — их нельзя сохранять."""
    m = mark()
    send(client, message=f"Ссылка не открылась {m}", page="/reset-password?token=SECRET123#x")
    assert find(admin, m)[0]["page"] == "/reset-password"
    m2 = mark()
    send(client, message=f"Другая страница {m2}", page="https://evil.example/path")
    assert find(admin, m2)[0]["page"] == ""


@cloud_only
def test_html_is_stored_verbatim(client, admin):
    m = mark()
    send(client, message=f'<script>alert("x")</script> {m}')
    assert find(admin, m)[0]["message"] == f'<script>alert("x")</script> {m}'


@cloud_only
@pytest.mark.parametrize("over,field", [
    ({"message": ""}, "message"), ({"message": "  а "}, "message"), ({"message": "я" * 3001}, "message"),
    ({"email": "not-an-email"}, "email"), ({"type": "hack"}, "type"), ({"elapsed_ms": -5}, "elapsed_ms"),
])
def test_validation(client, over, field):
    r = send(client, **over)
    assert r.status_code == 422 and field in str(r.json()["detail"])


@cloud_only
def test_optional_fields_can_be_omitted(client, admin):
    m = mark()
    r = client.post("/api/feedback", json={"message": f"Просто текст {m}"})
    assert r.status_code == 200
    item = find(admin, m)[0]
    assert (item["type"], item["email"], item["name"], item["status"]) == ("other", "", "", "new")


@cloud_only
def test_same_client_id_is_not_duplicated(client, admin, fake_net):
    """Двойной клик или повтор после обрыва связи: обращение одно, письмо одно."""
    m, cid = mark(), uuid.uuid4().hex
    assert send(client, message=f"Дубль {m}", client_id=cid).status_code == 200
    assert send(client, message=f"Дубль {m}", client_id=cid).status_code == 200
    assert len(find(admin, m)) == 1
    assert len(fake_net.formspree_calls) == 1


@cloud_only
def test_two_users_with_identical_text_are_both_kept(client, admin):
    """Дубли определяются по ключу формы, а не по тексту: два разных человека могут написать одно и то же."""
    m = mark()
    send(client, message=f"Всё отлично {m}", client_id=uuid.uuid4().hex)
    send(client, message=f"Всё отлично {m}", client_id=uuid.uuid4().hex)
    assert len(find(admin, m)) == 2


# ───────────────────────── ловушка ─────────────────────────

@cloud_only
def test_honeypot_marks_spam_without_telling_the_bot(client, admin, fake_net):
    m = mark()
    ok = send(client, message=f"Купите SEO {m}", hp="http://spam.example")
    assert ok.status_code == 200 and ok.json() == {"ok": True}       # ответ бота неотличим от обычного
    assert find(admin, m) == []                                       # в основном списке спама нет
    [item] = find(admin, m, status="spam")
    assert item["spam_reason"] == "honeypot" and item["forward_status"] == "off"
    assert fake_net.formspree_calls == []                             # не расходует лимит Formspree и не засоряет почту


@cloud_only
def test_too_fast_submission_is_spam_but_boundary_is_not(client, admin, relaxed):
    fast, edge, slow = mark(), mark(), mark()
    send(client, message=f"быстро {fast}", elapsed_ms=300)
    send(client, message=f"граница {edge}", elapsed_ms=1000)
    send(client, message=f"медленно {slow}", elapsed_ms=45_000)
    assert find(admin, fast, "spam")[0]["spam_reason"] == "too_fast"
    assert len(find(admin, edge)) == 1 and len(find(admin, slow)) == 1


@cloud_only
def test_many_links_is_spam_but_normal_links_are_fine(client, admin, relaxed):
    spam, normal = mark(), mark()
    send(client, message=f"{spam} http://a.ru http://b.ru https://c.ru www.d.ru")
    send(client, message=f"Вот ошибка https://flowmind.ru/workflow/12 и скриншот https://i.imgur.com/x.png, доки https://flowmind.ru/help/ {normal}")
    assert find(admin, spam, "spam")[0]["spam_reason"] == "links"
    assert len(find(admin, normal)) == 1


@cloud_only
@pytest.mark.parametrize("name,over", [
    ("api-клиент без служебных полей", {"elapsed_ms": None}),
    ("пробелы в скрытом поле (не считаются заполнением)", {"hp": "   "}),
    ("текст целиком на русском с эмодзи", {"message": "Спасибо, всё работает 👍 Но кнопка «Сохранить» иногда не нажимается"}),
    ("длинный вставленный текст", {"message": "Строка лога: ошибка соединения.\n" * 80}),
    ("текст ровно на лимите", {"message_len": 3000}),
    ("минимально короткий отзыв", {"message": "Ок!"}),
    ("код и спецсимволы", {"message": "{{input}} → SELECT * FROM t WHERE a='b'; <b>тест</b> &amp; 100%"}),
    ("три ссылки на документацию", {"message": "Смотрите https://a.ru/1 https://a.ru/2 https://a.ru/3"}),
    ("форма заполнена за 1,5 секунды (заранее скопированный текст)", {"elapsed_ms": 1500}),
])
def test_real_users_are_never_flagged(client, admin, relaxed, name, over):
    """Ловушка не должна принимать за спам обычных людей — ни в одном из типичных сценариев."""
    m = mark()
    over = dict(over)
    if "message_len" in over:
        over["message"] = "я" * (over.pop("message_len") - len(f" {m}"))
    over["message"] = f"{over.get('message', 'Нормальное обращение')} {m}"
    assert len(over["message"]) <= 3000
    assert send(client, **over).status_code == 200, name
    [item] = find(admin, m)
    assert item["status"] == "new" and item["spam_reason"] == "", name


@cloud_only
def test_restoring_false_positive_forwards_it(client, admin, fake_net, relaxed):
    """Если ловушка всё-таки сработала на живом человеке, админ возвращает обращение — и оно сразу уходит на почту."""
    m = mark()
    send(client, message=f"Автозаполнение испортило поле {m}", hp="Москва")
    item = find(admin, m, "spam")[0]
    assert fake_net.formspree_calls == []
    r = admin.patch(f"/admin/feedback/{item['id']}", json={"status": "new"})
    assert r.status_code == 200 and r.json()["status"] == "new"
    assert len(fake_net.formspree_calls) == 1
    assert find(admin, m)[0]["forward_status"] == "sent"


@cloud_only
def test_rate_limit_per_minute_keeps_the_text_recoverable(client):
    codes = [send(client).status_code for _ in range(7)]
    assert codes == [200] * 5 + [429, 429]
    r = send(client)
    assert r.status_code == 429 and "Подождите" in r.json()["detail"]["message"]


@cloud_only
def test_hourly_limit_is_not_stingy_for_shared_networks():
    """За одним IP (колледж, офис) сидят несколько тестировщиков: часового лимита должно хватать на целую группу."""
    limiter = ratelimit.feedback_hour_limiter
    assert (limiter.limit, limiter.window) == (40, 3600)
    fresh = ratelimit.RateLimiter(limit=limiter.limit, window_seconds=limiter.window)
    assert all(fresh.allow("1.2.3.4") for _ in range(40)) and not fresh.allow("1.2.3.4")


# ───────────────────────── копия в Formspree ─────────────────────────

@cloud_only
@pytest.mark.parametrize("mode", ["http500", "rejected", "network"])
def test_formspree_failure_never_loses_feedback(client, admin, fake_net, relaxed, mode):
    fake_net.formspree_mode = mode
    m = mark()
    r = send(client, message=f"Formspree лежит {m}")
    assert r.status_code == 200                                # пользователь получает успех
    item = find(admin, m)[0]
    assert item["status"] == "new" and item["forward_status"] == "failed"

    fake_net.formspree_mode = "ok"                             # Formspree ожил — повторная отправка из админки
    r = admin.post(f"/admin/feedback/{item['id']}/forward")
    assert r.status_code == 200 and r.json() == {"forward_status": "sent"}
    assert find(admin, m)[0]["forward_status"] == "sent"


@cloud_only
def test_forwarding_can_be_switched_off(client, admin, fake_net, monkeypatch):
    monkeypatch.setattr(settings, "formspree_url", "")
    m = mark()
    assert send(client, message=f"Без пересылки {m}").status_code == 200
    assert find(admin, m)[0]["forward_status"] == "off" and fake_net.formspree_calls == []
    r = admin.post(f"/admin/feedback/{find(admin, m)[0]['id']}/forward")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "formspree_off"


@cloud_only
def test_foreign_formspree_url_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "formspree_url", "https://evil.example/f/abc")
    assert settings.formspree_endpoint == "" and "FORMSPREE_URL" in settings.contacts_problems


@cloud_only
def test_spam_cannot_be_forwarded_manually(client, admin, relaxed):
    m = mark()
    send(client, message=f"бот {m}", hp="x")
    r = admin.post(f"/admin/feedback/{find(admin, m, 'spam')[0]['id']}/forward")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "is_spam"


# ───────────────────────── админка ─────────────────────────

@cloud_only
def test_admin_endpoints_require_admin(client, user):
    assert client.get("/api/admin/feedback").status_code == 401
    for method, url in [("get", "/admin/feedback"), ("get", "/admin/feedback/export.csv"), ("patch", "/admin/feedback/1"),
                        ("delete", "/admin/feedback/1"), ("delete", "/admin/feedback?status=spam"), ("post", "/admin/feedback/1/forward")]:
        kwargs = {"json": {"status": "done"}} if method == "patch" else {}
        assert getattr(user, method)(url, **kwargs).status_code == 403, url


@cloud_only
def test_admin_list_filters_search_pagination_and_counts(client, admin, relaxed):
    m = mark()
    for i in range(3):
        send(client, message=f"список {i} {m}", type="bug" if i == 0 else "idea")
    send(client, message=f"бот {m}", hp="x")
    assert len(find(admin, m)) == 3 and len(find(admin, m, "spam")) == 1
    page = admin.get("/admin/feedback", params={"q": m, "limit": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert admin.get("/admin/feedback", params={"q": m, "limit": 2, "offset": 2}).json()["items"][0]["message"].startswith("список 0")   # новые сверху
    assert admin.get("/admin/feedback", params={"q": m, "type": "bug"}).json()["total"] == 1
    assert admin.get("/admin/feedback", params={"q": m.upper()}).json()["total"] == 3                      # поиск без учёта регистра
    counts = page["counts"]
    assert set(counts) == {"new", "in_progress", "done", "spam"} and counts["new"] >= 3 and counts["spam"] >= 1
    assert admin.get("/admin/feedback", params={"status": "weird"}).status_code == 400
    assert admin.get("/admin/feedback", params={"type": "weird"}).status_code == 400


@cloud_only
def test_admin_status_note_delete_and_audit(client, admin):
    m = mark()
    send(client, message=f"для статусов {m}")
    fid = find(admin, m)[0]["id"]
    r = admin.patch(f"/admin/feedback/{fid}", json={"status": "in_progress", "admin_note": "  уточнить у пользователя "})
    assert r.status_code == 200 and (r.json()["status"], r.json()["admin_note"]) == ("in_progress", "уточнить у пользователя")
    assert admin.patch(f"/admin/feedback/{fid}", json={"status": "bogus"}).status_code == 400
    assert admin.patch("/admin/feedback/99999999", json={"status": "done"}).status_code == 404
    assert admin.delete(f"/admin/feedback/{fid}").status_code == 200
    assert find(admin, m) == [] and admin.delete(f"/admin/feedback/{fid}").status_code == 404
    assert any(a["action"] == "feedback.delete" and a["target"] == str(fid) for a in admin.get("/admin/audit").json())


@cloud_only
def test_bulk_delete_removes_only_spam(client, admin, relaxed):
    keep, bot = mark(), mark()
    send(client, message=f"живой {keep}")
    send(client, message=f"бот {bot}", hp="x")
    assert admin.delete("/admin/feedback").status_code == 400
    assert admin.delete("/admin/feedback?status=new").status_code == 400          # нельзя снести всё одним запросом
    assert admin.delete("/admin/feedback?status=spam").json()["deleted"] >= 1
    assert len(find(admin, keep)) == 1 and find(admin, bot, "spam") == []


@cloud_only
def test_dashboard_counts_new_feedback(client, admin):
    before = admin.get("/admin/stats").json()["feedback_new"]
    send(client)
    assert admin.get("/admin/stats").json()["feedback_new"] == before + 1


@cloud_only
def test_csv_export_is_excel_friendly_and_formula_safe(client, admin, relaxed):
    m = mark()
    send(client, message=f'=HYPERLINK("http://evil.example","жми") {m}', name="@админ", email="")
    send(client, message=f"Обычный текст; с точкой с запятой и «кавычками» {m}\nвторая строка")
    r = admin.get("/admin/feedback/export.csv", params={"q": m})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and r.headers["content-disposition"].endswith('.csv"')
    assert r.content.startswith(b"\xef\xbb\xbf")                                            # BOM: Excel увидит UTF-8
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0][:5] == ["id", "created_at", "status", "type", "name"]
    by_msg = {row[8]: row for row in rows[1:]}
    formula = next(v for k, v in by_msg.items() if "HYPERLINK" in k)
    assert formula[8].startswith("'=") and formula[4] == "'@админ"                          # формула обезврежена
    normal = next(v for k, v in by_msg.items() if "точкой с запятой" in k)
    assert "«кавычками»" in normal[8] and "\nвторая строка" in normal[8]                    # кириллица и переводы строк целы


# ───────────────────────── контакты и конфиг ─────────────────────────

@cloud_only
def test_contacts_in_public_config(client, monkeypatch):
    monkeypatch.setattr(settings, "support_email", "help@flowmind.example")
    monkeypatch.setattr(settings, "support_telegram", "flowmind_support")
    monkeypatch.setattr(settings, "support_vk", "vk.com/flowmind")
    cfg = client.get("/api/config").json()
    assert cfg["feedback_enabled"] is True
    assert cfg["contacts"] == {"email": "help@flowmind.example", "telegram": {"label": "@flowmind_support", "url": "https://t.me/flowmind_support"},
                               "vk": {"label": "vk.com/flowmind", "url": "https://vk.com/flowmind"}}


@cloud_only
def test_bad_contacts_are_dropped_not_rendered(client, monkeypatch):
    monkeypatch.setattr(settings, "support_email", "javascript:alert(1)")
    monkeypatch.setattr(settings, "support_telegram", "https://t.me.evil.example/x")
    monkeypatch.setattr(settings, "support_vk", "https://vk.com.evil.example/x")
    assert client.get("/api/config").json()["contacts"] == {}
    assert set(settings.contacts_problems) == {"SUPPORT_EMAIL", "SUPPORT_TELEGRAM", "SUPPORT_VK"}


@cloud_only
def test_empty_contacts_are_hidden(client, monkeypatch):
    for name in ("support_email", "support_telegram", "support_vk"):
        monkeypatch.setattr(settings, name, "")
    assert client.get("/api/config").json()["contacts"] == {}


@cloud_only
def test_account_deletion_anonymizes_feedback(client, admin):
    s = register(client, password="password123")
    m = mark()
    client.post("/api/feedback", json=payload(message=f"перед удалением {m}", email="", name=""), headers=s.headers)
    assert find(admin, m)[0]["email"] == s.email
    assert s.delete("/me", json={"password": "password123"}).status_code == 200
    item = find(admin, m)[0]
    assert (item["email"], item["name"], item["user_id"]) == ("", "", None) and item["message"].startswith("перед удалением")


@pytest.mark.skipif(TEST_MODE != "local", reason="local only")
def test_feedback_is_off_in_local_mode(client):
    cfg = client.get("/api/config").json()
    assert cfg["feedback_enabled"] is False
    r = client.post("/api/feedback", json=payload())
    assert r.status_code == 404 and r.json()["detail"]["code"] == "feedback_disabled"
