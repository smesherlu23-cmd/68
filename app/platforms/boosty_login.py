"""Автоматический вход в Boosty с прохождением email-2FA.

У Boosty нет публичного API логина — раньше Bearer-токен веб-клиента
приходилось копировать вручную (см. boosty.py). Этот модуль вместо
этого управляет headless-браузером (Playwright): открывает форму входа,
вводит почту и пароль, дожидается кода подтверждения на почте (IMAP) и
вводит его, а сам токен сессии добывает, перехватывая заголовок
Authorization исходящих запросов страницы к api.boosty.to. Заодно, чтобы
не спрашивать имя блога, определяет его из ответов API текущего пользователя.

Разметка страниц Boosty нигде не документирована и может меняться —
вместо жёстких CSS-селекторов используется набор эвристик (по типу
поля, плейсхолдеру, подписи, тексту кнопки); при изменении вёрстки
Boosty правки нужно вносить в списки *_HINTS ниже.
"""

from __future__ import annotations

import email
import imaplib
import json
import os
import re
import time
from datetime import datetime, timezone
from email.message import Message
from urllib.parse import unquote
from email.utils import parsedate_to_datetime

import requests

from ..core.logger import log_event

SITE_URL = "https://boosty.to/"
# Вход у Boosty — модалка на главной; отдельной страницы логина нет.
# boosty.to/<slug> — это блог, поэтому /app и /app/login дают «Blog not found»;
# авторизованная «домашняя» — это лента на самом boosty.to/.
HOME_URL = "https://boosty.to/"
CURRENT_USER_URL = "https://api.boosty.to/v1/user/current"

GDPR_ACCEPT_TID = "GDPROFFER:ACCEPT_BUTTON"
SIGN_IN_TID = "COMMON_TOPMENU_TOPMENURIGHTUNAUTHORIZED:SIGN_IN"

_EMAIL_HINTS = ["email", "e-mail", "почта", "mail"]
_PASSWORD_HINTS = ["пароль", "password"]
_CODE_HINTS = ["код", "code", "подтвержд", "verif"]
_SUBMIT_HINTS = ["войти", "продолжить", "log in", "sign in", "continue",
                 "далее", "подтвердить", "confirm"]
# Кнопки, раскрывающие ввод e-mail на первом (выбор способа) шаге модалки.
_EMAIL_METHOD_HINTS = ["e-mail", "email", "почт", "по e-mail", "по электронной",
                       "continue with e-mail", "войти по"]
# Тексты кнопок согласия на баннере cookie/GDPR (перекрывает клик по «Войти»).
_COOKIE_ACCEPT_HINTS = ["принять", "принимаю", "accept", "согласен", "разрешить",
                        "хорошо", "ок", "ok", "got it", "allow"]

_CODE_RE = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")

_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/125.0.0.0 Safari/537.36")

_STEALTH_JS = """
    try {
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    } catch (e) {}
    try {
        Object.defineProperty(navigator, 'languages',
            {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
    } catch (e) {}
    try {
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    } catch (e) {}
    try {
        window.chrome = window.chrome || {runtime: {}};
        const _query = window.navigator.permissions &&
            window.navigator.permissions.query;
        if (_query) {
            window.navigator.permissions.query = (params) =>
                params && params.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : _query(params);
        }
    } catch (e) {}
"""


class BoostyLoginError(RuntimeError):
    """Автоматический вход не удался (форма, почта или таймаут)."""


def _debug_enabled() -> bool:
    """CENTURIO_BOOSTY_DEBUG=1 — видимый браузер и дамп cookie/localStorage/
    скриншот в storage/boosty_debug (для разбора, когда токен не берётся)."""
    return os.environ.get("CENTURIO_BOOSTY_DEBUG", "").strip().lower() in (
        "1", "true", "yes", "on")


def _launch_browser(pw, debug: bool = False):
    """Запускает браузер для автовхода (в debug — видимый и с замедлением).

    Сначала пробуем Chromium, скачанный Playwright. Если он не установлен
    (частый случай, когда cdn.playwright.dev недоступен и `playwright install`
    не проходит), откатываемся на уже установленные в системе Microsoft Edge и
    Google Chrome — их скачивать не нужно. Канал можно жёстко задать через
    переменную окружения CENTURIO_BROWSER_CHANNEL (chromium/msedge/chrome)."""
    base: dict = {
        "headless": not debug,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--lang=ru-RU",
        ],
    }
    if debug:
        base["slow_mo"] = 300
    forced = os.environ.get("CENTURIO_BROWSER_CHANNEL", "").strip().lower()
    if forced in ("chromium", ""):
        attempts: list[dict] = [{}]
    else:
        attempts = [{"channel": forced}]
    if not forced:
        attempts += [{"channel": "msedge"}, {"channel": "chrome"}]

    last_exc: Exception | None = None
    for kwargs in attempts:
        try:
            return pw.chromium.launch(**base, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise BoostyLoginError(
        "не удалось запустить браузер для автовхода. Установите браузер "
        "командой «playwright install chromium» либо поставьте Google Chrome / "
        "Microsoft Edge в систему (они подхватятся автоматически). "
        f"Причина: {last_exc}")


def _collect_diag(page, context) -> dict:
    """Снимок состояния страницы для диагностики неудачного автовхода."""
    diag: dict = {"url": "", "title": "", "cookies": [],
                  "storage_keys": [], "session_keys": []}
    try:
        diag["url"] = page.url
    except Exception:  # noqa: BLE001
        pass
    try:
        diag["title"] = page.title()
    except Exception:  # noqa: BLE001
        pass
    try:
        diag["cookies"] = [c.get("name", "") for c in context.cookies()]
    except Exception:  # noqa: BLE001
        pass
    try:
        diag["storage_keys"] = page.evaluate(
            "() => Object.keys(window.localStorage)")
    except Exception:  # noqa: BLE001
        pass
    try:
        diag["session_keys"] = page.evaluate(
            "() => Object.keys(window.sessionStorage)")
    except Exception:  # noqa: BLE001
        pass
    return diag


def _diag_summary(diag: dict) -> str:
    cookies = ", ".join(diag.get("cookies") or []) or "нет"
    keys = ", ".join(diag.get("storage_keys") or []) or "нет"
    session = ", ".join(diag.get("session_keys") or []) or "нет"
    return (f"Итоговая страница: {diag.get('url') or '?'}; "
            f"cookies: {cookies}; localStorage: {keys}; "
            f"sessionStorage: {session}.")


def _dump_debug(page, diag: dict, form_html: str = "") -> None:
    """Сохраняет скриншот и текстовый дамп в storage/boosty_debug.
    form_html — снимок открытой модалки логина (важнее итоговой страницы)."""
    try:
        from ..core.paths import data_dir
        out = data_dir() / "boosty_debug"
        out.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(out / "login.png"), full_page=True)
        except Exception:  # noqa: BLE001
            pass
        try:
            (out / "page.html").write_text(page.content(), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        if form_html:
            try:
                (out / "form.html").write_text(form_html, encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        (out / "login.txt").write_text(
            f"url: {diag.get('url')}\n"
            f"title: {diag.get('title')}\n"
            f"cookies: {diag.get('cookies')}\n"
            f"localStorage: {diag.get('storage_keys')}\n"
            f"sessionStorage: {diag.get('session_keys')}\n",
            encoding="utf-8")
        log_event("boosty", f"Диагностика автовхода сохранена в {out}")
    except Exception as exc:  # noqa: BLE001
        log_event("boosty", f"Не удалось сохранить диагностику: {exc}", "WARNING")


def auto_login(login_email: str, login_password: str,
                mail_host: str, mail_port: int,
                mail_user: str, mail_password: str,
                timeout_ms: int = 45_000) -> tuple[str, str, str]:
    """Логинится на boosty.to, проходит email-2FA (если запросили), возвращает
    (bearer_token, cookie_header, blog_name) свежей сессии. blog_name может быть
    пустым, если определить его не удалось."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BoostyLoginError(
            "не установлен пакет playwright "
            "(pip install playwright && playwright install chromium)") from exc

    captured: dict[str, str] = {}

    def on_request(request) -> None:
        if "api.boosty.to" not in request.url:
            return
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            if len(token) > 20:
                captured["token"] = token

    def on_response(response) -> None:
        url = response.url
        if "api.boosty.to" not in url:
            return
        if "token" in captured and "blog" in captured:
            return
        if "application/json" not in response.headers.get("content-type", ""):
            return
        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            return
        # Токен из тела берём только у auth-эндпоинтов (иначе можно поймать
        # чужое поле "token" из обычного ответа API); заголовок Authorization
        # (on_request) остаётся приоритетным источником.
        auth_endpoint = any(m in url.lower()
                            for m in ("oauth", "auth", "login", "session"))
        if "token" not in captured and auth_endpoint:
            token = _find_token(data)
            if token:
                captured["token"] = token
        if "blog" not in captured:
            blog = _find_blog(data)
            if blog:
                captured["blog"] = blog

    debug = _debug_enabled()
    diag: dict = {}
    form_html = ""
    with sync_playwright() as pw:
        browser = _launch_browser(pw, debug=debug)
        try:
            context = browser.new_context(
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                viewport={"width": 1366, "height": 768},
                user_agent=_USER_AGENT,
                extra_http_headers={
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"},
            )
            try:
                context.add_init_script(_STEALTH_JS)
            except Exception:  # noqa: BLE001
                pass
            context.on("request", on_request)
            context.on("response", on_response)
            page = context.new_page()

            page.goto(SITE_URL, wait_until="networkidle", timeout=timeout_ms)
            opened = _open_login_form(page, timeout_ms=25_000)
            try:
                form_html = page.content()
            except Exception:  # noqa: BLE001
                pass
            if not opened:
                log_event("boosty", "Автовход: форма входа не открылась "
                          "(баннер cookie, анти-бот или изменение вёрстки).",
                          "WARNING")

            _fill_by_hints(page, "input", _EMAIL_HINTS, login_email)
            if not _fill_by_hints(page, "input[type=password]", _PASSWORD_HINTS,
                                   login_password):
                _click_by_hints(page, _SUBMIT_HINTS)
                pw_input = _wait_for_hints(page, "input[type=password]",
                                           _PASSWORD_HINTS, timeout_ms=10_000)
                if pw_input is not None:
                    pw_input.fill(login_password)
            _click_by_hints(page, _SUBMIT_HINTS)

            since = time.time()
            code_input = _wait_for_hints(page, "input", _CODE_HINTS,
                                        timeout_ms=15_000)
            if code_input is not None:
                code = _fetch_verification_code(mail_host, mail_port, mail_user,
                                                mail_password, since)
                code_input.fill(code)
                _click_by_hints(page, _SUBMIT_HINTS)

            try:
                page.goto(HOME_URL, wait_until="networkidle", timeout=timeout_ms)
            except Exception:  # noqa: BLE001
                page.wait_for_timeout(3000)
            if "token" not in captured:
                page.wait_for_timeout(1500)
            if "token" not in captured:
                try:
                    page.reload(wait_until="networkidle", timeout=timeout_ms)
                except Exception:  # noqa: BLE001
                    page.wait_for_timeout(2000)
            if "token" not in captured:
                found = (_token_from_cookies(context.cookies())
                         or _token_from_storage(page))
                if found:
                    captured["token"] = found

            cookie_header = "; ".join(f"{c['name']}={c['value']}"
                                      for c in context.cookies())
            diag = _collect_diag(page, context)
            if debug or "token" not in captured:
                _dump_debug(page, diag, form_html)
        finally:
            browser.close()

    token = captured.get("token")
    if not token:
        log_event("boosty", "Автовход: токен не получен. " + _diag_summary(diag),
                  "ERROR")
        hint = ("" if debug else
                " Для разбора запустите с переменной окружения "
                "CENTURIO_BOOSTY_DEBUG=1 — откроется видимый браузер, а "
                "скриншот и дамп сохранятся в storage/boosty_debug.")
        raise BoostyLoginError(
            "вход выполнен, но не удалось получить токен доступа. "
            + _diag_summary(diag) + hint)

    blog = captured.get("blog") or _fetch_blog_via_api(token)
    log_event("boosty", "Автовход выполнен, токен сессии получен"
              + (f", блог: {blog}" if blog else ""))
    return token, cookie_header, blog


def _visible_attrs(el) -> str:
    return " ".join(filter(None, [
        el.get_attribute("placeholder"),
        el.get_attribute("aria-label"),
        el.get_attribute("name"),
        el.get_attribute("type"),
    ])).lower()


def _fill_by_hints(page, selector: str, hints: list[str], value: str) -> bool:
    for el in page.locator(selector).all():
        try:
            if not el.is_visible():
                continue
            if any(h in _visible_attrs(el) for h in hints):
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def _click_by_hints(page, hints: list[str]) -> bool:
    for el in page.locator("button, [role=button], input[type=submit]").all():
        try:
            if not el.is_visible():
                continue
            text = (el.inner_text() or "").lower()
            value = (el.get_attribute("value") or "").lower()
            if any(h in text or h in value for h in hints):
                el.click()
                return True
        except Exception:
            continue
    return False


def _click_test_id(page, test_id: str) -> bool:
    """Кликает по элементу с data-test-id (стабильные якоря Boosty)."""
    try:
        el = page.query_selector(f'[data-test-id="{test_id}"]')
        if el is not None and el.is_visible():
            el.click()
            page.wait_for_timeout(600)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _dismiss_cookie_banner(page) -> None:
    """Закрывает баннер cookie/GDPR — он перекрывает клик по кнопке «Войти».
    Сначала пробуем известный data-test-id, затем кнопку с текстом согласия."""
    if _click_test_id(page, GDPR_ACCEPT_TID):
        return
    _click_by_hints(page, _COOKIE_ACCEPT_HINTS)


def _open_login_form(page, timeout_ms: int) -> bool:
    """Открывает модалку входа Boosty и ждёт появления поля ввода.

    На главной есть SSR-кнопка «Войти» (data-test-id SIGN_IN), но обработчик
    навешивается только после гидрации React — клик сразу после networkidle
    часто не открывает модалку. Поэтому кликаем повторно. Модалка вдобавок
    бывает двухшаговой (выбор способа → поле e-mail): если ввода нет, жмём
    кнопку «по e-mail». Возвращает True, когда появилось видимое поле."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        _dismiss_cookie_banner(page)
        if not _click_test_id(page, SIGN_IN_TID):
            _click_by_hints(page, ["войти", "log in", "sign in"])
        if _wait_for_any_input(page, timeout_ms=4_000):
            return True
        if _click_by_hints(page, _EMAIL_METHOD_HINTS):
            if _wait_for_any_input(page, timeout_ms=4_000):
                return True
    return False


def _wait_for_any_input(page, timeout_ms: int) -> bool:
    """Ждёт появления любого видимого поля ввода — признак открытой формы."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for el in page.locator("input").all():
            try:
                if el.is_visible():
                    return True
            except Exception:
                continue
        page.wait_for_timeout(400)
    return False


def _wait_for_hints(page, selector: str, hints: list[str], timeout_ms: int):
    """Ждёт появления поля, подходящего под hints (напр. поле кода после
    отправки формы входа); возвращает None, если 2FA не запрошена."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        for el in page.locator(selector).all():
            try:
                if el.is_visible() and any(h in _visible_attrs(el) for h in hints):
                    return el
            except Exception:
                continue
        page.wait_for_timeout(500)
    return None


def _token_from_cookies(cookies: list[dict]) -> str:
    """Ищет access-токен в cookie сессии Boosty. Значение cookie `auth` — это
    URL-кодированный JSON вида {"accessToken": "...", ...}; сначала проверяем
    cookie с «auth» в имени, затем любые, чьё значение — подходящий JSON."""
    def priority(c: dict) -> int:
        return 0 if "auth" in (c.get("name") or "").lower() else 1

    for cookie in sorted(cookies, key=priority):
        token = _token_from_json_str(unquote(cookie.get("value") or ""))
        if token:
            return token
    return ""


def _token_from_json_str(raw: str) -> str:
    try:
        return _find_token(json.loads(raw))
    except (ValueError, TypeError):
        return ""


def _find_token(data) -> str:
    """Достаёт строку access-токена из произвольного JSON (ключи accessToken/
    access_token/token/bearer); короткие значения игнорируем."""
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for key in ("accessToken", "access_token", "token", "bearer"):
                value = cur.get(key)
                if isinstance(value, str) and len(value) > 20:
                    return value
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return ""


def _find_blog(data) -> str:
    """Ищет slug блога текущего пользователя в произвольном JSON-ответе API
    (ключи blogUrl/blog_url или вложенный объект blog с url/blogUrl)."""
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for key in ("blogUrl", "blog_url"):
                slug = _slug(cur.get(key))
                if slug:
                    return slug
            nested = cur.get("blog")
            if isinstance(nested, dict):
                for key in ("blogUrl", "url"):
                    slug = _slug(nested.get(key))
                    if slug:
                        return slug
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return ""


def _slug(value) -> str:
    """Из строки вида "https://boosty.to/blogname" или "blogname/" достаёт slug."""
    if not isinstance(value, str) or not value.strip():
        return ""
    return value.strip().rstrip("/").split("/")[-1]


def _fetch_blog_via_api(token: str) -> str:
    """Резерв: спрашиваем блог напрямую у API текущего пользователя."""
    try:
        resp = requests.get(CURRENT_USER_URL,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=20)
        if resp.status_code == 200:
            return _find_blog(resp.json())
    except (requests.RequestException, ValueError) as exc:
        log_event("boosty", f"Не удалось определить блог через API: {exc}",
                  "WARNING")
    return ""


def _token_from_storage(page) -> str:
    """Резервный способ достать токен: типичные ключи local/sessionStorage
    SPA-клиентов (Boosty может держать сессию в любом из них)."""
    script = """
        () => {
            const jwtLike = /^[A-Za-z0-9-_]+\\.[A-Za-z0-9-_]+\\.[A-Za-z0-9-_]+$/;
            const stores = [window.localStorage, window.sessionStorage];
            for (const store of stores) {
                if (!store) continue;
                for (const key of Object.keys(store)) {
                    const raw = store.getItem(key);
                    if (!raw) continue;
                    if (jwtLike.test(raw) && raw.length > 20) return raw;
                    try {
                        const parsed = JSON.parse(raw);
                        const stack = [parsed];
                        while (stack.length) {
                            const cur = stack.pop();
                            if (!cur || typeof cur !== 'object') continue;
                            for (const f of ['accessToken', 'access_token',
                                             'token', 'bearer']) {
                                if (typeof cur[f] === 'string' &&
                                    cur[f].length > 20) return cur[f];
                            }
                            for (const v of Object.values(cur)) stack.push(v);
                        }
                    } catch (e) { /* не JSON — пропускаем */ }
                }
            }
            return '';
        }
    """
    try:
        return page.evaluate(script) or ""
    except Exception:
        return ""


def _fetch_verification_code(host: str, port: int, user: str, password: str,
                             since_ts: float, timeout: float = 90,
                             poll_interval: float = 3) -> str:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    since_date = datetime.now(timezone.utc).strftime("%d-%b-%Y")
    while time.time() < deadline:
        try:
            with imaplib.IMAP4_SSL(host, port) as imap:
                imap.login(user, password)
                imap.select("INBOX")
                status, data = imap.search(
                    None, f'(FROM "boosty" SINCE "{since_date}")')
                if status == "OK" and data and data[0]:
                    for msg_id in reversed(data[0].split()[-5:]):
                        status, msg_data = imap.fetch(msg_id, "(RFC822)")
                        if status != "OK" or not msg_data or not msg_data[0]:
                            continue
                        msg = email.message_from_bytes(msg_data[0][1])
                        if _message_ts(msg) < since_ts - 60:
                            continue
                        code = _code_in_message(msg)
                        if code:
                            return code
        except imaplib.IMAP4.error as exc:
            last_error = exc
            log_event("boosty", f"Ошибка почты при получении кода: {exc}", "ERROR")
        time.sleep(poll_interval)
    detail = f" ({last_error})" if last_error else ""
    raise BoostyLoginError(
        f"код подтверждения не пришёл на почту за отведённое время{detail}")


def _message_ts(msg: Message) -> float:
    date_header = msg.get("Date")
    if not date_header:
        return time.time()
    try:
        return parsedate_to_datetime(date_header).timestamp()
    except (TypeError, ValueError):
        return time.time()


def _code_in_message(msg: Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_type() not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="ignore")
        except LookupError:
            text = payload.decode("utf-8", errors="ignore")
        match = _CODE_RE.search(text)
        if match:
            return match.group(1)
    return ""
