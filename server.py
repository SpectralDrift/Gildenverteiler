"""Lokaler Webserver für den Gildenverteiler (nur Python-Standardbibliothek)."""

import argparse
from dataclasses import dataclass
from getpass import getpass
import hashlib
from http.cookies import SimpleCookie
import json
import os
import re
import secrets
import threading
import time
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from optimizer import optimize


PROJECT_DIR = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_DIR / "static"
CONFIG_DIR = PROJECT_DIR / "configurations"
DEFAULT_VIKINGS_FILE = PROJECT_DIR / "default_vikings.json"
VIKING_NAME_PATTERN = re.compile(r"[A-Za-zÄÖÜäöüß0-9_. ]{1,50}\Z")
GUILD_NAME_PATTERN = re.compile(r"[A-Za-zÄÖÜäöüß0-9]{1,50}\Z")
CONFIG_NAME_PATTERN = re.compile(r"[A-Za-zÄÖÜäöüß0-9_.-]{1,50}\Z")
SESSION_COOKIE = "gilden_session"
SESSION_LIFETIME = 12 * 60 * 60
CONFIG_WRITE_LOCK = threading.Lock()
GUILD_MINIMUM_SIZES = [2, 2, 2, 5, 4, 3]
GUILD_MAXIMUM_SIZES = [3, 3, 3, 6, 5, 4]
DEFAULT_VIKING_COUNT = 18


@dataclass
class Session:
    expires: float
    csrf_token: str


class Authentication:
    """Passwortprüfung und kurzlebige Sitzungen."""

    def __init__(self, password: str, secure_cookies: bool = True):
        self.salt = secrets.token_bytes(16)
        self.password_hash = self._hash(password)
        self.secure_cookies = secure_cookies
        self.sessions: dict[str, Session] = {}
        self.lock = threading.Lock()

    def _hash(self, password: str) -> bytes:
        return hashlib.scrypt(password.encode("utf-8"), salt=self.salt, n=2**14, r=8, p=1)

    def login(self, address: str, password: object) -> tuple[str, Session] | None:
        now = time.time()
        valid = isinstance(password, str) and secrets.compare_digest(self._hash(password), self.password_hash)
        if not valid:
            return None
        with self.lock:
            token = secrets.token_urlsafe(32)
            session = Session(now + SESSION_LIFETIME, secrets.token_urlsafe(32))
            self.sessions[token] = session
            return token, session

    def session(self, token: str | None) -> Session | None:
        if not token:
            return None
        now = time.time()
        with self.lock:
            session = self.sessions.get(token)
            if session is None or session.expires <= now:
                self.sessions.pop(token, None)
                return None
            return session

    def logout(self, token: str | None) -> None:
        if token:
            with self.lock:
                self.sessions.pop(token, None)


def validate_request(data: object) -> tuple[list[str], list[str], list[list[int | None]], list[int], list[int]]:
    if not isinstance(data, dict):
        raise ValueError("Ungültige Anfrage.")
    guilds = data.get("guilds")
    minimum_sizes = data.get("guildMinimumSizes")
    maximum_sizes = data.get("guildMaximumSizes")
    if minimum_sizes is None and maximum_sizes is None:
        legacy_sizes = data.get("guildSizes", [None] * 6)
        if not isinstance(legacy_sizes, list) or len(legacy_sizes) != 6:
            raise ValueError("Die Angaben zu den Gildengrößen sind ungültig.")
        minimum_sizes = [size if size is not None else GUILD_MINIMUM_SIZES[index]
                         for index, size in enumerate(legacy_sizes)]
        maximum_sizes = [size if size is not None else GUILD_MAXIMUM_SIZES[index]
                         for index, size in enumerate(legacy_sizes)]
    vikings = data.get("vikings")
    if not isinstance(guilds, list) or len(guilds) != 6:
        raise ValueError("Bitte genau 6 Gilden angeben.")
    if not isinstance(vikings, list) or not 1 <= len(vikings) <= 20:
        raise ValueError("Bitte 1 bis 20 Wikinger angeben.")
    if (not isinstance(minimum_sizes, list) or len(minimum_sizes) != 6
            or not isinstance(maximum_sizes, list) or len(maximum_sizes) != 6):
        raise ValueError("Die Angaben zu den Gildengrößen sind ungültig.")
    if (any(type(size) is not int or not 2 <= size <= 8
            for size in minimum_sizes + maximum_sizes)
            or any(minimum > maximum
                   for minimum, maximum in zip(minimum_sizes, maximum_sizes))):
        raise ValueError("Minimum und Maximum müssen ganze Zahlen zwischen 2 und 8 sein; das Minimum darf nicht größer sein.")

    guild_names = [name.strip() if isinstance(name, str) else "" for name in guilds]
    if any(not GUILD_NAME_PATTERN.fullmatch(name) for name in guild_names):
        raise ValueError(
            "Gildennamen dürfen höchstens 50 Zeichen lang sein und nur Buchstaben, "
            "deutsche Umlaute und Ziffern enthalten."
        )
    if len(set(guild_names)) != len(guild_names):
        raise ValueError("Gildennamen müssen eindeutig sein.")

    names: list[str] = []
    rankings: list[list[int | None]] = []
    for item in vikings:
        if not isinstance(item, dict):
            raise ValueError("Ungültiger Wikinger-Eintrag.")
        raw_name = item.get("name", "")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        ranking = item.get("ranking")
        if not name:
            raise ValueError("Jeder Wikinger braucht einen Namen.")
        if not VIKING_NAME_PATTERN.fullmatch(name):
            raise ValueError(
                f"Der Name {name!r} darf höchstens 50 Zeichen lang sein und nur "
                "Buchstaben, deutsche Umlaute, Ziffern, Leerzeichen, Punkte und Unterstriche enthalten."
            )
        if not isinstance(ranking, list) or len(ranking) != len(guild_names):
            raise ValueError(f"Die Rangliste von {name} ist unvollständig.")
        explicit = [value for value in ranking if value is not None]
        if any(type(value) is not int or not 0 <= value < len(guild_names) for value in explicit):
            raise ValueError(f"Die Rangliste von {name} enthält eine ungültige Gilde.")
        if len(set(explicit)) != len(explicit):
            raise ValueError(f"Die Rangliste von {name} enthält eine Gilde mehrfach.")
        ranking = list(ranking)
        if ranking.count(None) == 1:
            missing_guild = next(guild for guild in range(len(guild_names)) if guild not in explicit)
            ranking[ranking.index(None)] = missing_guild
        names.append(name)
        rankings.append(ranking)
    if len(set(names)) != len(names):
        raise ValueError("Wikingernamen müssen eindeutig sein.")
    resolve_size_limits(len(names), minimum_sizes, maximum_sizes)
    return guild_names, names, rankings, minimum_sizes, maximum_sizes


def resolve_size_limits(
    viking_count: int, minimum_sizes: list[int], maximum_sizes: list[int]
) -> tuple[list[int], list[int]]:
    """Prüfe, ob die frei gewählten Größenbereiche gemeinsam erfüllbar sind."""
    if sum(minimum_sizes) > viking_count or sum(maximum_sizes) < viking_count:
        raise ValueError("Die Gildengrößen passen nicht zur Anzahl der Wikinger.")
    return minimum_sizes, maximum_sizes


def validate_configuration(data: object) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Nicht unterstütztes Konfigurationsformat.")
    guilds, names, rankings, minimum_sizes, maximum_sizes = validate_request(data)
    return {
        "version": 1,
        "guilds": guilds,
        "guildMinimumSizes": minimum_sizes,
        "guildMaximumSizes": maximum_sizes,
        "vikings": [
            {"name": name, "ranking": ranking}
            for name, ranking in zip(names, rankings)
        ],
    }


def load_default_vikings() -> list[str]:
    """Lade lokale Standardnamen oder erzeuge eine neutrale Ersatzliste."""
    generic = [f"Wikinger{index}" for index in range(1, DEFAULT_VIKING_COUNT + 1)]
    if DEFAULT_VIKINGS_FILE.is_symlink() or not DEFAULT_VIKINGS_FILE.is_file():
        return generic
    try:
        data = json.loads(DEFAULT_VIKINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return generic
    if (not isinstance(data, list) or not 1 <= len(data) <= 20
            or any(not isinstance(name, str) or not VIKING_NAME_PATTERN.fullmatch(name.strip()) for name in data)):
        return generic
    names = [name.strip() for name in data]
    return names if len(set(names)) == len(names) else generic


def assigned_preference(ranking: list[int | None], guild: int) -> tuple[int, bool]:
    """Gib Wunschstufe und Kennzeichen für eine gleichwertige Gilde zurück."""
    if guild in ranking:
        return ranking.index(guild) + 1, False
    return ranking.index(None) + 1, True


def configuration_path(name: object) -> Path:
    if not isinstance(name, str) or not CONFIG_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Der Konfigurationsname darf höchstens 50 Zeichen lang sein und nur "
            "Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche enthalten."
        )
    target = (CONFIG_DIR / f"{name}.json").resolve()
    if target.parent != CONFIG_DIR.resolve():
        raise ValueError("Ungültiger Konfigurationsname.")
    return target


def save_configuration(target: Path, config: dict) -> None:
    """Schreibe eine Konfiguration atomar und kollisionsfrei."""
    temporary_path: Path | None = None
    with CONFIG_WRITE_LOCK:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=CONFIG_DIR,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(config, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def delete_configuration(target: Path) -> None:
    with CONFIG_WRITE_LOCK:
        if not target.is_file() or target.is_symlink():
            raise ValueError("Konfiguration wurde nicht gefunden.")
        target.unlink()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    @property
    def auth(self) -> Authentication:
        return self.server.auth  # type: ignore[attr-defined]

    def _session_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _session(self) -> Session | None:
        return self.auth.session(self._session_token())

    def _require_session(self, api: bool = True) -> Session | None:
        session = self._session()
        if session is not None:
            return session
        if api:
            self._json_response(401, {"error": "Bitte zuerst anmelden."})
        else:
            self.send_response(303)
            self.send_header("Location", "/login.html")
            self.end_headers()
        return None

    def _read_json(self) -> object:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Ungültige Anfragegröße.") from error
        if not 0 < length <= 1_000_000:
            raise ValueError("Anfrage ist leer oder zu groß.")
        return json.loads(self.rfile.read(length))

    def _require_csrf(self, session: Session) -> None:
        supplied = self.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(supplied, session.csrf_token):
            raise ValueError("Ungültiger Sicherheitsschlüssel. Bitte Seite neu laden.")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/login.html", "/login.js", "/style.css"}:
            if parsed.path == "/login.html" and self._session() is not None:
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()
                return
            super().do_GET()
            return
        if parsed.path == "/api/session":
            session = self._require_session()
            if session is not None:
                self._json_response(200, {
                    "csrfToken": session.csrf_token,
                    "defaultVikings": load_default_vikings(),
                })
            return
        if self._require_session(api=parsed.path.startswith("/api/")) is None:
            return
        if parsed.path == "/api/configurations":
            names = sorted(
                path.stem
                for path in CONFIG_DIR.glob("*.json")
                if not path.is_symlink() and path.is_file()
            )
            self._json_response(200, {"configurations": names})
            return
        if parsed.path == "/api/configurations/load":
            try:
                name = parse_qs(parsed.query).get("name", [None])[0]
                target = configuration_path(name)
                if not target.is_file() or target.is_symlink():
                    raise ValueError("Konfiguration wurde nicht gefunden.")
                config = validate_configuration(json.loads(target.read_text(encoding="utf-8")))
                self._json_response(200, config)
            except (ValueError, json.JSONDecodeError, OSError) as error:
                self._json_response(400, {"error": str(error)})
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/login.html", "/login.js", "/style.css"}:
            super().do_HEAD()
            return
        if self._require_session(api=parsed.path.startswith("/api/")) is None:
            return
        super().do_HEAD()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/login":
            try:
                data = self._read_json()
                password = data.get("password") if isinstance(data, dict) else None
                result = self.auth.login(self.client_address[0], password)
                if result is None:
                    self._json_response(401, {"error": "Passwort ist nicht korrekt."})
                    return
                token, _ = result
                attributes = [f"{SESSION_COOKIE}={token}", "Path=/", "HttpOnly", "SameSite=Strict", f"Max-Age={SESSION_LIFETIME}"]
                if self.auth.secure_cookies:
                    attributes.append("Secure")
                self._json_response(200, {"ok": True}, {"Set-Cookie": "; ".join(attributes)})
            except (ValueError, json.JSONDecodeError, OSError) as error:
                self._json_response(400, {"error": str(error)})
            return
        allowed = {"/api/logout", "/api/optimize", "/api/configurations/save", "/api/configurations/delete"}
        if path not in allowed:
            self.send_error(404)
            return
        session = self._require_session()
        if session is None:
            return
        try:
            self._require_csrf(session)
            data = self._read_json()
            if path == "/api/logout":
                self.auth.logout(self._session_token())
                cookie = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
                if self.auth.secure_cookies:
                    cookie += "; Secure"
                self._json_response(200, {"ok": True}, {"Set-Cookie": cookie})
                return
            if path == "/api/configurations/save":
                target = configuration_path(data.get("name") if isinstance(data, dict) else None)
                config = validate_configuration(data.get("configuration") if isinstance(data, dict) else None)
                save_configuration(target, config)
                self._json_response(200, {"saved": target.stem})
                return
            if path == "/api/configurations/delete":
                target = configuration_path(data.get("name") if isinstance(data, dict) else None)
                delete_configuration(target)
                self._json_response(200, {"deleted": target.stem})
                return
            guilds, names, rankings, minimum_sizes, maximum_sizes = validate_request(data)
            result = optimize(rankings, len(guilds), minimum_sizes, maximum_sizes)
            groups = [{"name": guild, "members": []} for guild in guilds]
            for index, (name, guild_index) in enumerate(zip(names, result.assignment)):
                rank, equal = assigned_preference(rankings[index], guild_index)
                groups[guild_index]["members"].append({"name": name, "rank": rank, "equal": equal})
            payload = {
                "groups": groups,
                "score": result.score,
                "maximumScore": result.maximum_score,
                "optimalSolutionCount": result.optimal_solution_count,
            }
            self._json_response(200, payload)
        except (ValueError, json.JSONDecodeError, OSError) as error:
            self._json_response(400, {"error": str(error)})

    def end_headers(self) -> None:
        # Die kleine lokale Anwendung wird häufig während des Betriebs geändert.
        # Kein Cache verhindert gemischte Versionen von HTML und JavaScript.
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def _json_response(self, status: int, payload: dict, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Webseite zur optimalen Gildenverteilung")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8888, type=int)
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Cookies auch über unverschlüsseltes HTTP erlauben (nur für lokale Tests)",
    )
    args = parser.parse_args()
    while True:
        password = getpass("Gemeinsames Passwort (mindestens 16 Zeichen): ")
        if len(password) < 16:
            print("Das Passwort ist zu kurz.")
            continue
        if password != getpass("Passwort wiederholen: "):
            print("Die Passwörter stimmen nicht überein.")
            continue
        break
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.auth = Authentication(password, secure_cookies=not args.allow_insecure_http)  # type: ignore[attr-defined]
    password = ""
    print(f"Gildenverteiler läuft auf http://{args.host}:{args.port}")
    if args.allow_insecure_http:
        print("WARNUNG: Unsichere HTTP-Cookies sind aktiviert.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer beendet.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
