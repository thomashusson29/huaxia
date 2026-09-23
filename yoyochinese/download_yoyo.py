#!/usr/bin/env python3
"""Export accessible Yoyo Chinese videos, PDFs, and Anki flashcards.

The crawler only uses media URLs exposed by each lesson page and skips content
that the current Yoyo Chinese session marks as locked.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import unicodedata
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from huaxia_tags import (  # noqa: E402
    TagContext,
    YoyoCoursePath,
    build_managed_tags,
)

try:
    from .anki_export import AnkiExportError, ensure_genanki_available, export_course_packages
    from .anki_connect import (
        AnkiConnectError,
        DEFAULT_DECK_NAME as ANKI_CONNECT_DECK,
        sync_packages as sync_anki_connect,
    )
    from .audio_fallback import generate_fallback_audio
except ImportError:  # Script execution from the yoyochinese directory.
    from anki_export import AnkiExportError, ensure_genanki_available, export_course_packages
    from anki_connect import (
        AnkiConnectError,
        DEFAULT_DECK_NAME as ANKI_CONNECT_DECK,
        sync_packages as sync_anki_connect,
    )
    from audio_fallback import generate_fallback_audio


SITE_URL = "https://yoyochinese.com"
PAGE_HOSTS = {"yoyochinese.com", "www.yoyochinese.com"}
MEDIA_HOSTS = {"video.yoyochinese.com", "cdn.yoyochinese.com"}
LECTURE_NOTES_ROOT = (
    "https://cdn.yoyochinese.com/attachment/PDF/LectureNotes/"
)
LOGIN_URL = f"{SITE_URL}/api/v1/auth/login"
FLASHCARDS_URL = f"{SITE_URL}/api/v1/flashcards/lesson"
PRACTICE_AUDIO_ROOT = "https://cdn.yoyochinese.com/audio/practice/"
KEYCHAIN_EMAIL_SERVICE = "fr.yoyochinese.downloader.email"
KEYCHAIN_PASSWORD_SERVICE = "fr.yoyochinese.downloader.password"
KEYCHAIN_ACCOUNT = "default"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
YOYO_DATA_RE = re.compile(
    r"<script[^>]*>\s*window\.yoyoData\s*=\s*(\{.*?\})\s*</script>",
    re.DOTALL,
)


class YoyoError(RuntimeError):
    pass


@dataclass(frozen=True)
class Asset:
    kind: str
    url: str
    path: str


@dataclass(frozen=True)
class LessonRef:
    lesson_url: str
    course_slug: str
    course_title: str
    course_code: str
    level_number: int
    level_title: str
    unit_slug: str
    unit_prefix: str
    unit_title: str
    lesson_number: int
    lesson_prefix: str
    lesson_title: str


@dataclass
class FlashcardPlan:
    flashcard_id: str
    code: str
    index_number: int
    simplified: str
    traditional: str
    pinyin: str
    english: str
    tags: list[str]
    assets: list[Asset]


@dataclass
class LessonPlan:
    lesson_url: str
    lesson_id: str
    code: str
    title: str
    course: str
    course_title: str
    course_code: str
    level_number: int
    level_title: str
    unit: str
    unit_title: str
    lesson_number: int
    directory: str
    assets: list[Asset]
    flashcards_available: bool = False
    flashcards: list[FlashcardPlan] = field(default_factory=list)
    skipped_reason: str = ""


def _keychain_read(service: str) -> str | None:
    try:
        completed = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                KEYCHAIN_ACCOUNT,
                "-s",
                service,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise YoyoError(f"Impossible de consulter le Trousseau macOS: {exc}") from exc
    if completed.returncode != 0:
        return None
    return completed.stdout.rstrip("\n")


def load_keychain_credentials() -> tuple[str, str] | None:
    email = _keychain_read(KEYCHAIN_EMAIL_SERVICE)
    password = _keychain_read(KEYCHAIN_PASSWORD_SERVICE)
    if not email and not password:
        return None
    if not email or not password:
        raise YoyoError(
            "Les identifiants Yoyo Chinese du Trousseau sont incomplets. "
            "Relancez Configurer le compte.command."
        )
    return email, password


def _keychain_write(service: str, value: str) -> None:
    encoded_value = value.encode("utf-8").hex()
    security_command = (
        f"add-generic-password -U -a {KEYCHAIN_ACCOUNT} "
        f"-s {service} -X {encoded_value}\n"
    )
    try:
        completed = subprocess.run(
            ["security", "-i"],
            input=security_command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise YoyoError(f"Impossible d’écrire dans le Trousseau macOS: {exc}") from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or "commande security refusée"
        raise YoyoError(f"Impossible d’écrire dans le Trousseau macOS: {message}")
    if _keychain_read(service) != value:
        raise YoyoError("Le Trousseau macOS n’a pas confirmé l’enregistrement.")


def configure_keychain_credentials() -> None:
    print("Configuration sécurisée du compte Yoyo Chinese.")
    print("Les identifiants seront enregistrés dans le Trousseau macOS.")
    email = input("Adresse e-mail Yoyo Chinese : ").strip()
    if "@" not in email:
        raise YoyoError("Adresse e-mail invalide.")
    password = getpass.getpass("Mot de passe Yoyo Chinese : ")
    confirmation = getpass.getpass("Confirmez le mot de passe : ")
    if not password:
        raise YoyoError("Le mot de passe ne peut pas être vide.")
    if password != confirmation:
        raise YoyoError("Les deux mots de passe ne correspondent pas.")
    _keychain_write(KEYCHAIN_EMAIL_SERVICE, email)
    _keychain_write(KEYCHAIN_PASSWORD_SERVICE, password)
    print("Identifiants enregistrés dans le Trousseau macOS.")


class PageClient:
    def __init__(
        self,
        timeout: int = 60,
        cookie_file: Path | None = None,
        *,
        use_keychain: bool = True,
    ) -> None:
        self.timeout = timeout
        self.authenticated = False
        handlers: list[Any] = []
        jar: http.cookiejar.CookieJar
        if cookie_file:
            jar = http.cookiejar.MozillaCookieJar(str(cookie_file))
            try:
                jar.load(ignore_discard=True, ignore_expires=True)
            except (OSError, http.cookiejar.LoadError) as exc:
                raise YoyoError(
                    f"Impossible de lire le fichier de cookies {cookie_file}: {exc}"
                ) from exc
        else:
            jar = http.cookiejar.CookieJar()
        handlers.append(HTTPCookieProcessor(jar))
        self.opener = build_opener(*handlers)
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_lock = threading.Lock()
        if use_keychain and not cookie_file:
            credentials = load_keychain_credentials()
            if credentials:
                self.login(*credentials)

    def open(self, url: str, headers: dict[str, str] | None = None):
        request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if headers:
            request_headers.update(headers)
        request = Request(url, headers=request_headers)
        return self.opener.open(request, timeout=self.timeout)

    def fetch_text(self, url: str) -> str:
        try:
            with self.open(
                url,
                {"Accept": "text/html,application/xhtml+xml"},
            ) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise YoyoError(f"Impossible de charger {url}: {exc}") from exc
        return raw.decode(charset, errors="replace")

    def fetch_data(self, url: str) -> dict[str, Any]:
        url = canonical_page_url(url)
        with self._cache_lock:
            cached = self._cache.get(url)
        if cached is not None:
            return cached
        data = parse_yoyo_data(self.fetch_text(url), url)
        with self._cache_lock:
            self._cache[url] = data
        return data

    def fetch_json(self, url: str) -> Any:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in PAGE_HOSTS:
            raise YoyoError(f"URL d’API Yoyo Chinese refusée: {url}")
        try:
            with self.open(url, {"Accept": "application/json"}) as response:
                raw = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise YoyoError(f"Impossible de charger {url}: {exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise YoyoError(f"Réponse JSON Yoyo Chinese illisible: {url}") from exc

    def fetch_flashcards(self, lesson_id: str) -> list[dict[str, Any]]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", lesson_id):
            raise YoyoError(f"Identifiant de leçon refusé: {lesson_id!r}")
        value = self.fetch_json(f"{FLASHCARDS_URL}/{quote(lesson_id)}")
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise YoyoError(f"Flashcards Yoyo Chinese inattendues pour {lesson_id}")
        return value

    def login(self, email: str, password: str) -> None:
        payload = json.dumps({"email": email, "password": password}).encode("utf-8")
        request = Request(
            LOGIN_URL,
            data=payload,
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": SITE_URL,
                "Referer": f"{SITE_URL}/auth/login",
            },
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raw = exc.read()
            message = _login_error_message(raw) or str(exc)
            raise YoyoError(f"Connexion Yoyo Chinese refusée: {message}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise YoyoError(f"Connexion Yoyo Chinese impossible: {exc}") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise YoyoError("Réponse de connexion Yoyo Chinese illisible.") from exc
        if not isinstance(result, dict):
            raise YoyoError("Réponse de connexion Yoyo Chinese inattendue.")
        if result.get("error"):
            raise YoyoError(f"Connexion Yoyo Chinese refusée: {result['error']}")
        if result.get("isEmailConfirmed") is False:
            raise YoyoError("L’adresse e-mail Yoyo Chinese n’est pas confirmée.")
        self.authenticated = True


def _login_error_message(raw: bytes) -> str:
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(result, dict):
        return ""
    return str(result.get("error") or result.get("message") or "")


def canonical_page_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in PAGE_HOSTS:
        raise YoyoError("Utilisez une URL https://yoyochinese.com/...")
    if not parsed.path.startswith(("/lesson/", "/unit/", "/courses")):
        raise YoyoError("L’URL doit viser une leçon, une unité ou le catalogue /courses.")
    path = re.sub(r"/{2,}", "/", parsed.path)
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(("https", "yoyochinese.com", path, "", ""))


def parse_yoyo_data(html_text: str, page_url: str = "la page") -> dict[str, Any]:
    match = YOYO_DATA_RE.search(html_text)
    if not match:
        raise YoyoError(f"Données window.yoyoData introuvables dans {page_url}.")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise YoyoError(f"Données Yoyo Chinese illisibles dans {page_url}.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("initialPageData"), dict):
        raise YoyoError(f"Structure Yoyo Chinese inattendue dans {page_url}.")
    return data


def _absolute_page_url(value: str) -> str:
    return canonical_page_url(urljoin(SITE_URL, value))


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _number_from_label(value: Any, fallback: int = 0) -> int:
    match = re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match else fallback


def _lesson_base_path(value: str) -> str:
    path = urlsplit(value).path.rstrip("/")
    activity = path.rsplit("/", 1)[-1]
    if activity in {
        "ask",
        "audio",
        "dialogue",
        "flashcards",
        "notes",
        "overview",
        "pinyin",
        "quiz",
        "video",
    }:
        path = path.rsplit("/", 1)[0]
    return path


def _lesson_refs_from_unit(data: dict[str, Any]) -> list[LessonRef]:
    page = data["initialPageData"]
    if page.get("isUnitLocked"):
        return []
    course_slug = str(page.get("courseSlug") or "course")
    course_title = str(page.get("courseTitle") or course_slug)
    course_code = str(page.get("courseCode") or "")
    level_number = int(page.get("levelNumber") or 0)
    level_title = f"Level {level_number}" if level_number else "Level"
    unit_slug = str(page.get("unitSlug") or page.get("unitId") or "unit")
    unit_prefix = str(page.get("unitPrefix") or "Unit")
    unit_title = str(page.get("unitTitle") or unit_prefix)
    refs: list[LessonRef] = []
    for lesson in page.get("lessons", []):
        if isinstance(lesson, dict) and isinstance(lesson.get("url"), str):
            lesson_number = int(
                lesson.get("indexNumber")
                or _number_from_label(lesson.get("prefix"))
                or len(refs) + 1
            )
            refs.append(
                LessonRef(
                    lesson_url=_absolute_page_url(lesson["url"]),
                    course_slug=course_slug,
                    course_title=course_title,
                    course_code=course_code,
                    level_number=level_number,
                    level_title=level_title,
                    unit_slug=unit_slug,
                    unit_prefix=unit_prefix,
                    unit_title=unit_title,
                    lesson_number=lesson_number,
                    lesson_prefix=str(lesson.get("prefix") or f"Lesson {lesson_number}"),
                    lesson_title=str(lesson.get("title") or f"Lesson {lesson_number}"),
                )
            )
    return refs


def _lesson_urls_from_unit(data: dict[str, Any]) -> list[str]:
    """Backward-compatible helper used by older integrations and tests."""
    return [ref.lesson_url for ref in _lesson_refs_from_unit(data)]


def _unit_urls_from_level(data: dict[str, Any]) -> list[str]:
    units = data["initialPageData"].get("units", [])
    urls = []
    for unit in units:
        if not isinstance(unit, dict) or unit.get("isUnitLocked"):
            continue
        slug = unit.get("unitSlug")
        if isinstance(slug, str) and slug:
            urls.append(_absolute_page_url(f"/unit/{slug}"))
    return _unique(urls)


def _level_urls(data: dict[str, Any]) -> list[str]:
    page = data["initialPageData"]
    slug = page.get("courseSlug")
    levels = page.get("reduxCourse", {}).get("levels", [])
    if not isinstance(slug, str) or not slug:
        raise YoyoError("Identifiant de cours introuvable.")
    count = max(1, len(levels))
    return [
        _absolute_page_url(f"/courses/{slug}" + ("" if number == 1 else f"/{number}"))
        for number in range(1, count + 1)
    ]


def _lesson_ref_from_page(data: dict[str, Any], lesson_url: str) -> LessonRef:
    page = data["initialPageData"]
    lesson = page.get("lesson", {})
    level = lesson.get("level", {}) if isinstance(lesson, dict) else {}
    unit = lesson.get("unit", {}) if isinstance(lesson, dict) else {}
    lesson_number = int(
        lesson.get("indexNumber")
        or _number_from_label(lesson.get("prefix"))
        or 0
    )
    level_number = _number_from_label(level.get("prefix"))
    overview_unit_title = page.get("overviewSectionProps", {}).get("unitTitle")
    unit_prefix = str(unit.get("prefix") or overview_unit_title or "Unit")
    unit_title = str(unit.get("title") or overview_unit_title or unit_prefix)
    return LessonRef(
        lesson_url=canonical_page_url(lesson_url),
        course_slug=str(page.get("courseSlug") or "course"),
        course_title=str(page.get("courseTitle") or page.get("courseSlug") or "Course"),
        course_code=str(page.get("courseCode") or lesson.get("course", {}).get("code") or ""),
        level_number=level_number,
        level_title=str(level.get("title") or level.get("prefix") or f"Level {level_number}"),
        unit_slug=str(page.get("unitSlug") or page.get("unitId") or "unit"),
        unit_prefix=unit_prefix,
        unit_title=unit_title,
        lesson_number=lesson_number,
        lesson_prefix=str(lesson.get("prefix") or f"Lesson {lesson_number}"),
        lesson_title=str(lesson.get("title") or page.get("lessonTitle") or "Lesson"),
    )


def discover_lesson_refs(
    start_url: str,
    client: PageClient,
    *,
    allow_all_courses: bool = False,
    limit: int | None = None,
) -> list[LessonRef]:
    """Resolve a lesson, unit, course, or catalog URL to accessible lessons."""
    start_url = canonical_page_url(start_url)
    start_data = client.fetch_data(start_url)
    page_id = start_data.get("initialPageId")
    if page_id == "lesson":
        page = start_data["initialPageData"]
        unit_slug = page.get("unitSlug")
        if isinstance(unit_slug, str) and unit_slug:
            unit_data = client.fetch_data(_absolute_page_url(f"/unit/{unit_slug}"))
            refs = _lesson_refs_from_unit(unit_data)
            lesson_path = _lesson_base_path(start_url)
            for ref in refs:
                if _lesson_base_path(ref.lesson_url) == lesson_path:
                    return [ref][:limit]
        return [_lesson_ref_from_page(start_data, start_url)][:limit]
    if page_id == "unit":
        return _lesson_refs_from_unit(start_data)[:limit]

    if page_id == "courses":
        if not allow_all_courses:
            raise YoyoError(
                "Le catalogue contient de très nombreux fichiers. Relancez avec "
                "--all-courses pour confirmer, ou utilisez l’URL d’un cours."
            )
        course_urls = [
            _absolute_page_url(course["url"])
            for course in start_data["initialPageData"].get("courses", [])
            if isinstance(course, dict) and isinstance(course.get("url"), str)
        ]
    elif page_id == "level":
        course_urls = [start_url]
    else:
        raise YoyoError(f"Type de page Yoyo Chinese non pris en charge: {page_id!r}")

    lesson_refs: list[LessonRef] = []
    seen_urls: set[str] = set()
    for course_url in course_urls:
        course_data = client.fetch_data(course_url)
        for level_url in _level_urls(course_data):
            level_data = client.fetch_data(level_url)
            for unit_url in _unit_urls_from_level(level_data):
                unit_data = client.fetch_data(unit_url)
                for ref in _lesson_refs_from_unit(unit_data):
                    if ref.lesson_url not in seen_urls:
                        seen_urls.add(ref.lesson_url)
                        lesson_refs.append(ref)
                if limit and len(lesson_refs) >= limit:
                    return lesson_refs[:limit]
    return lesson_refs[:limit]


def discover_lesson_urls(
    start_url: str,
    client: PageClient,
    *,
    allow_all_courses: bool = False,
    limit: int | None = None,
) -> list[str]:
    return [
        ref.lesson_url
        for ref in discover_lesson_refs(
            start_url,
            client,
            allow_all_courses=allow_all_courses,
            limit=limit,
        )
    ]


def safe_component(value: str, fallback: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return (value or fallback)[:120]


def numbered_folder(prefix: str, title: str, number: int, width: int = 2) -> str:
    label = re.sub(r"\s*\d+\s*$", "", prefix).strip() or prefix or "Item"
    if not number:
        number = _number_from_label(prefix)
    number_text = f"{number:0{width}d}" if number else "00"
    base = f"{label} {number_text}"
    equivalent_titles = {
        prefix.strip().casefold(),
        base.casefold(),
        f"{label} {number}".casefold(),
    }
    if title and title.strip().casefold() not in equivalent_titles:
        base += f" - {title.strip()}"
    return safe_component(base, f"{label} {number_text}")


def lecture_notes_url(filename: str) -> str:
    relative_path = _safe_media_relative_path(filename, "PDF")
    return LECTURE_NOTES_ROOT + quote(relative_path, safe="/")


def _safe_media_relative_path(value: str, label: str) -> str:
    value = value.strip()
    parts = value.split("/")
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise YoyoError(f"Nom de {label} refusé: {value!r}")
    return "/".join(parts)


def practice_audio_url(filename: str) -> str:
    filename = filename.strip()
    if not filename:
        raise YoyoError("Nom de fichier audio vide.")
    if filename.startswith("https://"):
        return validate_media_url(filename)
    filename = _safe_media_relative_path(filename, "fichier audio")
    if not filename.lower().endswith(".mp3"):
        filename += ".mp3"
    return validate_media_url(PRACTICE_AUDIO_ROOT + quote(filename, safe="/"))


def validate_media_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in MEDIA_HOSTS:
        raise YoyoError(f"URL de média refusée: {url}")
    return url


def build_lesson_plan(
    lesson_ref: LessonRef | str,
    data: dict[str, Any],
    output_root: Path,
    *,
    include_video: bool = True,
    include_pdf: bool = True,
) -> LessonPlan:
    if isinstance(lesson_ref, str):
        lesson_ref = _lesson_ref_from_page(data, lesson_ref)
    lesson_url = lesson_ref.lesson_url
    if data.get("initialPageId") != "lesson":
        raise YoyoError(f"La page n’est pas une leçon: {lesson_url}")
    page = data["initialPageData"]
    lesson = page.get("lesson", {})
    code = str(lesson.get("code") or page.get("lessonId") or "lesson")
    title = str(lesson.get("title") or page.get("lessonTitle") or code)
    course = lesson_ref.course_slug
    course_title = lesson_ref.course_title
    course_code = lesson_ref.course_code or str(page.get("courseCode") or "")
    level_number = lesson_ref.level_number
    level_title = lesson_ref.level_title
    unit = lesson_ref.unit_prefix
    unit_title = lesson_ref.unit_title
    lesson_number = lesson_ref.lesson_number or int(lesson.get("indexNumber") or 0)
    directory = (
        output_root
        / "Courses"
        / safe_component(course_title, course)
        / numbered_folder("Level", level_title, level_number)
        / numbered_folder(lesson_ref.unit_prefix, unit_title, _number_from_label(lesson_ref.unit_prefix), 3)
        / numbered_folder(lesson_ref.lesson_prefix, title, lesson_number)
    )
    plan = LessonPlan(
        lesson_url=lesson_url,
        lesson_id=str(page.get("lessonId") or lesson.get("_id") or ""),
        code=code,
        title=title,
        course=course,
        course_title=course_title,
        course_code=course_code,
        level_number=level_number,
        level_title=level_title,
        unit=unit,
        unit_title=unit_title,
        lesson_number=lesson_number,
        directory=str(directory),
        assets=[],
        flashcards_available=bool(
            page.get("practiceSectionProps", {}).get(
                "isShowFlashcards",
                lesson.get("isShowFlashcards", False),
            )
        ),
    )
    if page.get("isLocked") or lesson.get("isLocked"):
        plan.skipped_reason = "leçon verrouillée pour la session courante"
        return plan

    mp4_url = page.get("mp4Src")
    if (
        include_video
        and page.get("canWatchVideo") is not False
        and isinstance(mp4_url, str)
        and mp4_url
    ):
        plan.assets.append(
            Asset(
                "video",
                validate_media_url(mp4_url),
                str(directory / safe_component(f"{code}.mp4", "video.mp4")),
            )
        )

    practice = page.get("practiceSectionProps", {})
    lecture_file = practice.get("lectureFile") or lesson.get("lectureFile")
    show_lecture = practice.get("isShowLecture", lesson.get("isShowLecture", False))
    if include_pdf and show_lecture and isinstance(lecture_file, str) and lecture_file:
        pdf_url = validate_media_url(lecture_notes_url(lecture_file))
        plan.assets.append(
            Asset(
                "pdf",
                pdf_url,
                str(directory / safe_component(lecture_file.rsplit("/", 1)[-1], "notes.pdf")),
            )
        )

    return plan


def build_flashcard_plans(
    plan: LessonPlan,
    raw_cards: list[dict[str, Any]],
    *,
    audio_speed: str = "both",
) -> list[FlashcardPlan]:
    if audio_speed not in {"normal", "slow", "both"}:
        raise YoyoError(f"Vitesse audio Anki inconnue: {audio_speed}")
    unit_number = _number_from_label(plan.unit)
    course_path = YoyoCoursePath(
        course=plan.course_title,
        level=plan.level_number,
        unit=unit_number,
        lesson=plan.lesson_number,
    )
    audio_directory = Path(plan.directory) / "Flashcards" / "audio"
    cards: list[FlashcardPlan] = []
    for position, raw_card in enumerate(raw_cards, start=1):
        content = raw_card.get("content")
        if not isinstance(content, dict):
            continue
        simplified = str(content.get("simplified") or "").strip()
        traditional = str(content.get("traditional") or simplified).strip()
        if not simplified and not traditional:
            continue
        index_number = int(raw_card.get("indexNumber") or position)
        flashcard_id = str(raw_card.get("_id") or "")
        code = str(raw_card.get("code") or f"{plan.code}-{index_number:03d}")
        english_parts = [
            str(content.get(name) or "").strip()
            for name in ("english1", "english2")
        ]
        english = " / ".join(part for part in english_parts if part)
        assets: list[Asset] = []
        normal = str(content.get("normal") or "").strip()
        slow = str(content.get("slow") or "").strip()
        if audio_speed in {"normal", "both"} and normal:
            normal_name = Path(urlsplit(practice_audio_url(normal)).path).name
            assets.append(
                Asset(
                    "flashcard_audio_normal",
                    practice_audio_url(normal),
                    str(audio_directory / safe_component(normal_name, f"{code}-N.mp3")),
                )
            )
        if audio_speed in {"slow", "both"} and slow:
            slow_name = Path(urlsplit(practice_audio_url(slow)).path).name
            assets.append(
                Asset(
                    "flashcard_audio_slow",
                    practice_audio_url(slow),
                    str(audio_directory / safe_component(slow_name, f"{code}-S.mp3")),
                )
            )
        pinyin = str(content.get("pinyin") or "").strip()
        tags = build_managed_tags(
            TagContext(
                hanzi=simplified or traditional,
                traditional=traditional,
                pinyin=pinyin,
                course_paths=(course_path,),
            )
        )
        cards.append(
            FlashcardPlan(
                flashcard_id=flashcard_id,
                code=code,
                index_number=index_number,
                simplified=simplified or traditional,
                traditional=traditional,
                pinyin=pinyin,
                english=english,
                tags=list(tags),
                assets=assets,
            )
        )
    cards.sort(key=lambda card: (card.index_number, card.code, card.flashcard_id))
    return cards


def build_complete_lesson_plan(
    lesson_ref: LessonRef,
    client: PageClient,
    output_root: Path,
    *,
    include_video: bool,
    include_pdf: bool,
    include_anki: bool,
    audio_speed: str,
) -> LessonPlan:
    data = client.fetch_data(lesson_ref.lesson_url)
    plan = build_lesson_plan(
        lesson_ref,
        data,
        output_root,
        include_video=include_video,
        include_pdf=include_pdf,
    )
    if plan.skipped_reason:
        return plan
    if include_anki and plan.flashcards_available and plan.lesson_id:
        plan.flashcards = build_flashcard_plans(
            plan,
            client.fetch_flashcards(plan.lesson_id),
            audio_speed=audio_speed,
        )
    if not plan.assets and not plan.flashcards:
        selected = []
        if include_video:
            selected.append("MP4")
        if include_pdf:
            selected.append("PDF")
        if include_anki:
            selected.append("flashcard")
        plan.skipped_reason = "aucune ressource sélectionnée exposée par la page"
        if selected:
            plan.skipped_reason += f" ({', '.join(selected)})"
    return plan


def _content_total(headers: Any, offset: int) -> int | None:
    content_range = headers.get("Content-Range", "")
    match = re.search(r"/(\d+)$", content_range)
    if match:
        return int(match.group(1))
    content_length = headers.get("Content-Length")
    if content_length and content_length.isdigit():
        return int(content_length) + offset
    return None


def download_asset(
    asset: Asset,
    client: PageClient,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    target = Path(asset.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.stat().st_size > 0 and not overwrite:
        return {
            **asdict(asset),
            "status": "existing",
            "bytes": target.stat().st_size,
        }

    partial = target.with_name(target.name + ".part")
    if overwrite and partial.exists():
        partial.unlink()
    offset = partial.stat().st_size if partial.exists() else 0
    headers: dict[str, str] = {}
    if offset:
        headers["Range"] = f"bytes={offset}-"

    try:
        response = client.open(asset.url, headers)
    except HTTPError as exc:
        content_range = exc.headers.get("Content-Range", "")
        completed = re.search(r"\*/(\d+)$", content_range)
        if exc.code == 416 and offset and completed and offset == int(completed.group(1)):
            os.replace(partial, target)
            return {
                **asdict(asset),
                "status": "downloaded",
                "bytes": target.stat().st_size,
            }
        raise YoyoError(f"Échec du téléchargement {asset.url}: {exc}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise YoyoError(f"Échec du téléchargement {asset.url}: {exc}") from exc

    with response:
        status = getattr(response, "status", response.getcode())
        if offset and status != 206:
            offset = 0
        total = _content_total(response.headers, offset)
        mode = "ab" if offset and status == 206 else "wb"
        try:
            with partial.open(mode) as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        except OSError as exc:
            raise YoyoError(f"Impossible d’écrire {partial}: {exc}") from exc

    size = partial.stat().st_size
    if total is not None and size != total:
        raise YoyoError(
            f"Téléchargement incomplet pour {asset.url}: {size} / {total} octets"
        )
    os.replace(partial, target)
    return {**asdict(asset), "status": "downloaded", "bytes": size}


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def download_lesson(
    plan: LessonPlan,
    client: PageClient,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    result = asdict(plan)
    if plan.skipped_reason:
        result["status"] = "skipped"
        return result
    all_assets = list(plan.assets)
    for flashcard in plan.flashcards:
        all_assets.extend(flashcard.assets)
    downloaded: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, str]] = []
    for asset in all_assets:
        attempts = 3 if asset.kind.startswith("flashcard_audio_") else 1
        for attempt in range(1, attempts + 1):
            try:
                downloaded[asset.path] = download_asset(asset, client, overwrite=overwrite)
                break
            except (YoyoError, HTTPError, URLError, OSError) as exc:
                message = str(exc)
                transient = bool(
                    re.search(r"HTTP Error (?:429|5\d\d)", message)
                    or re.search(r"timed out|temporar|reset by peer", message, re.IGNORECASE)
                )
                if attempt < attempts and transient:
                    time.sleep(2 ** (attempt - 1))
                    continue
                downloaded[asset.path] = {
                    **asdict(asset),
                    "status": "error",
                    "error": message,
                    "attempts": attempt,
                }
                break

    for flashcard in plan.flashcards:
        for asset in flashcard.assets:
            failure = downloaded[asset.path]
            if failure.get("status") != "error":
                continue
            provider = generate_fallback_audio(flashcard.simplified, asset.path)
            if not provider:
                continue
            original_error = str(failure["error"])
            downloaded[asset.path] = {
                **asdict(asset),
                "status": "generated",
                "bytes": Path(asset.path).stat().st_size,
                "provider": provider,
                "original_source": "yoyo",
                "original_error": original_error,
            }
            warnings.append(
                {
                    "kind": asset.kind,
                    "url": asset.url,
                    "warning": original_error,
                    "fallback_provider": provider,
                }
            )

    errors = [
        {
            "kind": asset["kind"],
            "url": asset["url"],
            "error": asset["error"],
        }
        for asset in downloaded.values()
        if asset.get("status") == "error"
    ]

    result["assets"] = [downloaded[asset.path] for asset in plan.assets]
    flashcard_results: list[dict[str, Any]] = []
    for flashcard in plan.flashcards:
        card_result = asdict(flashcard)
        card_result["assets"] = [downloaded[asset.path] for asset in flashcard.assets]
        flashcard_results.append(card_result)
    result["flashcards"] = flashcard_results
    result["errors"] = errors
    result["warnings"] = warnings
    states = {asset["status"] for asset in downloaded.values()}
    if errors:
        result["status"] = "partial" if len(errors) < len(downloaded) else "error"
    elif len(states) == 1:
        result["status"] = states.pop()
    else:
        result["status"] = "updated"
    result["downloaded_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(Path(plan.directory) / "lesson.json", result)
    if flashcard_results:
        write_json_atomic(
            Path(plan.directory) / "Flashcards" / "flashcards.json",
            {
                "lesson_id": plan.lesson_id,
                "lesson_url": plan.lesson_url,
                "card_count": len(flashcard_results),
                "cards": flashcard_results,
            },
        )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exporter les MP4, PDF et flashcards Anki d’une leçon, d’une unité, "
            "d’un cours ou de tout le catalogue Yoyo Chinese."
        )
    )
    parser.add_argument("url", help="URL Yoyo Chinese à parcourir")
    parser.add_argument(
        "-o",
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent / "downloads",
        help="dossier de destination (par défaut: ./downloads)",
    )
    parser.add_argument("--workers", type=int, default=3, help="téléchargements parallèles")
    parser.add_argument("--limit", type=int, help="limiter le nombre de leçons")
    parser.add_argument("--dry-run", action="store_true", help="afficher sans télécharger")
    parser.add_argument("--overwrite", action="store_true", help="retélécharger les fichiers existants")
    parser.add_argument("--no-videos", action="store_true", help="ne pas télécharger les MP4")
    parser.add_argument("--no-pdfs", action="store_true", help="ne pas télécharger les PDF")
    parser.add_argument("--no-anki", action="store_true", help="ne pas télécharger ni créer les flashcards Anki")
    parser.add_argument(
        "--no-anki-connect",
        action="store_true",
        help="ne pas synchroniser avec AnkiConnect même si Anki est ouvert",
    )
    parser.add_argument(
        "--anki-connect-deck",
        default=ANKI_CONNECT_DECK,
        help=f"deck AnkiConnect (par défaut: {ANKI_CONNECT_DECK})",
    )
    parser.add_argument(
        "--anki-audio",
        choices=("normal", "slow", "both"),
        default="both",
        help="sons Anki à conserver (par défaut: normal et lent)",
    )
    parser.add_argument(
        "--all-courses",
        action="store_true",
        help="confirmer le parcours de tout le catalogue /courses",
    )
    parser.add_argument(
        "--cookie-file",
        type=Path,
        help="cookies Netscape exportés d’une session Yoyo Chinese autorisée",
    )
    parser.add_argument(
        "--no-keychain",
        action="store_true",
        help="ne pas utiliser les identifiants du Trousseau macOS",
    )
    parser.add_argument("--timeout", type=int, default=60, help="délai réseau en secondes")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 8:
        parser.error("--workers doit être compris entre 1 et 8")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit doit être positif")
    if args.timeout < 1:
        parser.error("--timeout doit être positif")
    if args.no_videos and args.no_pdfs and args.no_anki:
        parser.error("au moins un type de contenu doit être sélectionné")
    if not args.anki_connect_deck.strip():
        parser.error("--anki-connect-deck ne peut pas être vide")
    return args


def main() -> int:
    args = parse_args()
    try:
        include_video = not args.no_videos
        include_pdf = not args.no_pdfs
        include_anki = not args.no_anki
        if include_anki and not args.dry_run:
            ensure_genanki_available()

        client = PageClient(
            args.timeout,
            args.cookie_file,
            use_keychain=not args.no_keychain,
        )
        start_url = canonical_page_url(args.url)
        auth_label = "connectée" if client.authenticated else "publique"
        print(f"Session Yoyo Chinese: {auth_label}", file=sys.stderr)
        print(f"Découverte depuis {start_url}", file=sys.stderr)
        lesson_refs = discover_lesson_refs(
            start_url,
            client,
            allow_all_courses=args.all_courses,
            limit=args.limit,
        )
        print(f"{len(lesson_refs)} leçon(s) accessible(s) trouvée(s).", file=sys.stderr)

        plans: list[LessonPlan] = []
        errors: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    build_complete_lesson_plan,
                    ref,
                    client,
                    args.output_root,
                    include_video=include_video,
                    include_pdf=include_pdf,
                    include_anki=include_anki,
                    audio_speed=args.anki_audio,
                ): ref
                for ref in lesson_refs
            }
            for future in as_completed(futures):
                ref = futures[future]
                try:
                    plans.append(future.result())
                except Exception as exc:
                    errors.append(
                        {
                            "stage": "inventory",
                            "lesson_url": ref.lesson_url,
                            "error": str(exc),
                        }
                    )
                    print(f"[inventaire en erreur] {ref.lesson_url}: {exc}", file=sys.stderr)
        order = {ref.lesson_url: index for index, ref in enumerate(lesson_refs)}
        plans.sort(key=lambda plan: order[plan.lesson_url])
        flashcard_count = sum(len(plan.flashcards) for plan in plans)
        print(f"{flashcard_count} flashcard(s) trouvée(s).", file=sys.stderr)

        if args.dry_run:
            inventory = {
                "source": start_url,
                "authenticated": client.authenticated,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "discovered_lesson_count": len(lesson_refs),
                "planned_lesson_count": len(plans),
                "flashcard_count": flashcard_count,
                "error_count": len(errors),
                "options": {
                    "videos": include_video,
                    "pdfs": include_pdf,
                    "anki": include_anki,
                    "anki_audio": args.anki_audio,
                    "anki_connect": include_anki and not args.no_anki_connect,
                    "anki_connect_deck": args.anki_connect_deck,
                },
                "lessons": [asdict(plan) for plan in plans],
                "errors": errors,
            }
            print(json.dumps(inventory, ensure_ascii=False, indent=2))
            return 1 if errors else 0

        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    download_lesson,
                    plan,
                    client,
                    overwrite=args.overwrite,
                ): plan
                for plan in plans
            }
            for future in as_completed(futures):
                plan = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    for asset_error in result.get("errors", []):
                        errors.append(
                            {
                                "stage": "download",
                                "lesson_url": plan.lesson_url,
                                **asset_error,
                            }
                        )
                    state = result.get("status", "done")
                    print(f"[{state}] {plan.code} — {plan.title}", file=sys.stderr)
                except Exception as exc:  # preserve other downloads and report all failures
                    errors.append(
                        {
                            "stage": "download",
                            "lesson_url": plan.lesson_url,
                            "error": str(exc),
                        }
                    )
                    print(f"[erreur] {plan.code}: {exc}", file=sys.stderr)

        results.sort(key=lambda item: order.get(item["lesson_url"], len(order)))
        packages: list[dict[str, Any]] = []
        anki_connect: dict[str, Any] = {"status": "disabled"}
        if include_anki:
            selection = bool(args.limit) or urlsplit(start_url).path.startswith(
                ("/lesson/", "/unit/")
            )
            try:
                packages = export_course_packages(
                    plans,
                    args.output_root,
                    selection=selection,
                )
                for package in packages:
                    print(
                        f"[Anki] {package['course_title']} — "
                        f"{package['card_count']} carte(s)",
                        file=sys.stderr,
                    )
            except (AnkiExportError, OSError) as exc:
                errors.append({"stage": "anki", "error": str(exc)})
                print(f"[Anki en erreur] {exc}", file=sys.stderr)
            if not args.no_anki_connect:
                try:
                    anki_connect = sync_anki_connect(
                        [package["path"] for package in packages],
                        deck_name=args.anki_connect_deck,
                    )
                    if anki_connect["status"] == "synced":
                        print(
                            f"[AnkiConnect] {anki_connect['deck_name']} — "
                            f"{anki_connect['note_count']} note(s), "
                            f"{anki_connect['card_count']} carte(s)",
                            file=sys.stderr,
                        )
                    elif anki_connect["status"] == "unavailable":
                        print(
                            "[AnkiConnect] Anki n’est pas ouvert ou AnkiConnect "
                            "n’est pas disponible; les .apkg ont tout de même été créés.",
                            file=sys.stderr,
                        )
                except AnkiConnectError as exc:
                    anki_connect = {"status": "error", "error": str(exc)}
                    errors.append({"stage": "anki_connect", "error": str(exc)})
                    print(f"[AnkiConnect en erreur] {exc}", file=sys.stderr)

        manifest = {
            "source": start_url,
            "authenticated": client.authenticated,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "discovered_lesson_count": len(lesson_refs),
            "lesson_count": len(results),
            "flashcard_count": flashcard_count,
            "anki_package_count": len(packages),
            "error_count": len(errors),
            "options": {
                "videos": include_video,
                "pdfs": include_pdf,
                "anki": include_anki,
                "anki_audio": args.anki_audio,
                "anki_connect": include_anki and not args.no_anki_connect,
                "anki_connect_deck": args.anki_connect_deck,
            },
            "lessons": results,
            "anki_packages": packages,
            "anki_connect": anki_connect,
            "errors": errors,
        }
        write_json_atomic(args.output_root / "manifest.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    except (
        YoyoError,
        AnkiExportError,
        AnkiConnectError,
        HTTPError,
        URLError,
        OSError,
    ) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
