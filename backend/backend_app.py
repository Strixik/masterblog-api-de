import json
import os
import tempfile
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint


app = Flask(__name__)
CORS(app)

POSTS_FILE = Path(__file__).resolve().parent / "posts.json"

INITIAL_POSTS = [
    {
        "id": 1,
        "title": "First post",
        "content": "This is the first post.",
        "author": "Admin",
        "date": "2023-06-07",
    },
    {
        "id": 2,
        "title": "Second post",
        "content": "This is the second post.",
        "author": "Editor",
        "date": "2023-06-08",
    },
]

SWAGGER_URL = "/api/docs"
API_URL = "/static/masterblog.json"

swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={"app_name": "Masterblog API"},
)

app.register_blueprint(
    swagger_ui_blueprint,
    url_prefix=SWAGGER_URL,
)


class StorageError(Exception):
    """Fehler beim Lesen oder Schreiben der Beitragsdatei."""


def valid_date(value):
    """Prüft ein Datum im Format YYYY-MM-DD."""
    if not isinstance(value, str):
        return False

    try:
        parsed_date = date.fromisoformat(value)
        return parsed_date.isoformat() == value
    except ValueError:
        return False


def validate_text_fields(data, fields):
    """Prüft Textfelder und entfernt äußere Leerzeichen."""
    cleaned_fields = {}

    for field in fields:
        if field not in data:
            continue

        value = data[field]

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{field} muss Text sein und darf nicht leer sein."
            )

        cleaned_fields[field] = value.strip()

    return cleaned_fields


def save_posts(posts):
    """Speichert Beiträge atomar über eine temporäre Datei."""
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=POSTS_FILE.parent,
            prefix=".posts-",
            suffix=".json",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            json.dump(
                posts,
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.write("\n")

        os.replace(temporary_path, POSTS_FILE)

    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

        raise StorageError(
            "Beiträge konnten nicht gespeichert werden."
        ) from error


def load_posts():
    """Liest Beiträge und prüft die grundlegende Dateistruktur."""
    try:
        with POSTS_FILE.open(encoding="utf-8") as file:
            posts = json.load(file)

    except FileNotFoundError:
        # Beim ersten Start eine neue Datei mit Beispieldaten anlegen.
        posts = [post.copy() for post in INITIAL_POSTS]
        save_posts(posts)
        return posts

    except (OSError, json.JSONDecodeError) as error:
        raise StorageError(
            "Beitragsdatei konnte nicht gelesen werden."
        ) from error

    if not isinstance(posts, list):
        raise StorageError(
            "Beitragsdatei muss eine Liste enthalten."
        )

    for post in posts:
        if not isinstance(post, dict):
            raise StorageError(
                "Beitragsdatei enthält einen ungültigen Beitrag."
            )

        if type(post.get("id")) is not int:
            raise StorageError(
                "Jeder Beitrag muss eine ganzzahlige ID enthalten."
            )

        for field in ("title", "content", "author", "date"):
            if not isinstance(post.get(field), str):
                raise StorageError(
                    f"Das Feld {field} muss Text enthalten."
                )

        if not valid_date(post["date"]):
            raise StorageError(
                "Beitragsdatei enthält ein ungültiges Datum."
            )

    post_ids = [post["id"] for post in posts]

    if len(set(post_ids)) != len(post_ids):
        raise StorageError(
            "Beitragsdatei enthält doppelte IDs."
        )

    return posts


@app.errorhandler(StorageError)
def storage_error(error):
    """Gibt Speicherfehler als JSON-Antwort zurück."""
    app.logger.error("%s", error)

    return jsonify({
        "error": str(error),
    }), 500


@app.route("/api/posts", methods=["GET"])
def get_posts():
    """Gibt Beiträge optional sortiert zurück."""
    posts = load_posts()

    sort_field = request.args.get("sort")
    direction = request.args.get("direction", "asc")

    allowed_sort_fields = (
        "title",
        "content",
        "author",
        "date",
    )

    if (
        sort_field is not None
        and sort_field not in allowed_sort_fields
    ):
        return jsonify({
            "error": (
                "Ungültiges Sortierfeld. Erlaubt sind "
                "title, content, author und date."
            )
        }), 400

    if direction not in ("asc", "desc"):
        return jsonify({
            "error": (
                "Ungültige Sortierrichtung. "
                "Erlaubt sind asc und desc."
            )
        }), 400

    if sort_field is None:
        return jsonify(posts)

    def sort_key(post):
        """Erzeugt den Sortierschlüssel für einen Beitrag."""
        if sort_field == "date":
            return date.fromisoformat(post["date"])

        return post[sort_field].lower()

    sorted_posts = sorted(
        posts,
        key=sort_key,
        reverse=(direction == "desc"),
    )

    return jsonify(sorted_posts)


@app.route("/api/posts", methods=["POST"])
def add_post():
    """Erstellt und speichert einen neuen Beitrag."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Ein JSON-Objekt wird erwartet."
        }), 400

    required_fields = ("title", "content")

    missing_fields = [
        field
        for field in required_fields
        if field not in data
    ]

    if missing_fields:
        return jsonify({
            "error": "Pflichtfelder fehlen.",
            "fields": missing_fields,
        }), 400

    try:
        cleaned_fields = validate_text_fields(
            data,
            ("title", "content", "author"),
        )
    except ValueError as error:
        return jsonify({
            "error": str(error),
        }), 400

    post_date = data.get(
        "date",
        date.today().isoformat(),
    )

    if not valid_date(post_date):
        return jsonify({
            "error": "Datum muss im Format YYYY-MM-DD sein."
        }), 400

    posts = load_posts()

    new_post = {
        "id": max(
            (post["id"] for post in posts),
            default=0,
        ) + 1,
        "title": cleaned_fields["title"],
        "content": cleaned_fields["content"],
        "author": cleaned_fields.get(
            "author",
            "Unbekannt",
        ),
        "date": post_date,
    }

    posts.append(new_post)
    save_posts(posts)

    return jsonify(new_post), 201


@app.route("/api/posts/search", methods=["GET"])
def search_posts():
    """Sucht Beiträge in Titel, Inhalt, Autor und Datum."""
    posts = load_posts()

    search_query = request.args.get("search")
    title_query = request.args.get("title")
    content_query = request.args.get("content")

    queries = (
        search_query,
        title_query,
        content_query,
    )

    if all(query is None for query in queries):
        return jsonify(posts)

    matches = [
        post
        for post in posts
        if (
            search_query is not None
            and any(
                search_query.lower() in post[field].lower()
                for field in (
                    "title",
                    "content",
                    "author",
                    "date",
                )
            )
        )
        or (
            title_query is not None
            and title_query.lower() in post["title"].lower()
        )
        or (
            content_query is not None
            and content_query.lower() in post["content"].lower()
        )
    ]

    return jsonify(matches)


@app.route("/api/posts/<int:post_id>", methods=["DELETE"])
def delete_post(post_id):
    """Löscht einen Beitrag und speichert die Änderung."""
    posts = load_posts()

    post = next(
        (
            item
            for item in posts
            if item["id"] == post_id
        ),
        None,
    )

    if post is None:
        return jsonify({
            "error": (
                f"Beitrag mit der ID {post_id} "
                "wurde nicht gefunden."
            )
        }), 404

    posts.remove(post)
    save_posts(posts)

    return jsonify({
        "message": (
            f"Post with id {post_id} "
            "has been deleted successfully."
        )
    }), 200


@app.route("/api/posts/<int:post_id>", methods=["PUT"])
def update_post(post_id):
    """Aktualisiert einen Beitrag und speichert die Änderung."""
    posts = load_posts()

    post = next(
        (
            item
            for item in posts
            if item["id"] == post_id
        ),
        None,
    )

    if post is None:
        return jsonify({
            "error": (
                f"Beitrag mit der ID {post_id} "
                "wurde nicht gefunden."
            )
        }), 404

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Ein JSON-Objekt wird erwartet."
        }), 400

    try:
        cleaned_fields = validate_text_fields(
            data,
            ("title", "content", "author"),
        )
    except ValueError as error:
        return jsonify({
            "error": str(error),
        }), 400

    if "date" in data and not valid_date(data["date"]):
        return jsonify({
            "error": "Datum muss im Format YYYY-MM-DD sein."
        }), 400

    post.update(cleaned_fields)

    if "date" in data:
        post["date"] = data["date"]

    save_posts(posts)

    return jsonify(post), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5002,
        debug=True,
    )