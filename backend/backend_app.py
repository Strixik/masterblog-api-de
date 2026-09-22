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
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)


class StorageError(Exception):
    """Fehler beim Lesen oder Schreiben der Beitragsdatei."""


def save_posts(posts):
    """Speichert Beiträge über eine temporäre Datei."""
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
            json.dump(posts, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")

        os.replace(temporary_path, POSTS_FILE)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise StorageError("Beiträge konnten nicht gespeichert werden.") from error


def load_posts():
    """Liest Beiträge und prüft die grundlegende Dateistruktur."""
    try:
        with POSTS_FILE.open(encoding="utf-8") as file:
            posts = json.load(file)
    except FileNotFoundError:
        # Die Datei beim ersten Start mit Beispielbeiträgen anlegen.
        posts = INITIAL_POSTS
        save_posts(posts)
        return posts
    except (OSError, json.JSONDecodeError) as error:
        raise StorageError("Beitragsdatei konnte nicht gelesen werden.") from error

    if not isinstance(posts, list) or any(
        not isinstance(post, dict)
        or type(post.get("id")) is not int
        or any(
            not isinstance(post.get(field), str)
            for field in ("title", "content", "author", "date")
        )
        or not valid_date(post["date"])
        for post in posts
    ):
        raise StorageError("Beitragsdatei enthält ungültige Daten.")

    if len({post["id"] for post in posts}) != len(posts):
        raise StorageError("Beitragsdatei enthält doppelte IDs.")

    return posts


def valid_date(value):
    """Prüft ein Datum im Format YYYY-MM-DD."""
    if not isinstance(value, str):
        return False

    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


@app.errorhandler(StorageError)
def storage_error(error):
    """Gibt Speicherfehler als JSON zurück."""
    app.logger.error("%s", error)
    return jsonify({"error": str(error)}), 500


@app.route("/api/posts", methods=["GET"])
def get_posts():
    """Gibt Beiträge optional sortiert zurück."""
    posts = load_posts()
    sort_field = request.args.get("sort")
    direction = request.args.get("direction", "asc")

    if sort_field is not None and sort_field not in (
        "title", "content", "author", "date"
    ):
        return jsonify({
            "error": "Ungültiges Sortierfeld."
        }), 400

    if direction not in ("asc", "desc"):
        return jsonify({
            "error": "Ungültige Sortierrichtung. Erlaubt sind asc und desc."
        }), 400

    if sort_field is None:
        return jsonify(posts)

    if sort_field == "date":
        sort_key = lambda post: date.fromisoformat(post["date"])
    else:
        sort_key = lambda post: post[sort_field].lower()

    return jsonify(sorted(
        posts,
        key=sort_key,
        reverse=(direction == "desc"),
    ))


@app.route("/api/posts", methods=["POST"])
def add_post():
    """Erstellt und speichert einen Beitrag."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Ein JSON-Objekt wird erwartet."}), 400

    missing_fields = [
        field for field in ("title", "content") if field not in data
    ]
    if missing_fields:
        return jsonify({
            "error": "Pflichtfelder fehlen.",
            "fields": missing_fields,
        }), 400

    if not all(
        isinstance(data[field], str) and data[field].strip()
        for field in ("title", "content")
    ):
        return jsonify({
            "error": "Titel und Inhalt müssen nicht leerer Text sein."
        }), 400

    author = data.get("author", "Unbekannt")
    if not isinstance(author, str):
        return jsonify({"error": "Autor muss Text sein."}), 400

    post_date = data.get("date", date.today().isoformat())
    if not valid_date(post_date):
        return jsonify({
            "error": "Datum muss im Format YYYY-MM-DD sein."
        }), 400

    posts = load_posts()
    new_post = {
        "id": max((post["id"] for post in posts), default=0) + 1,
        "title": data["title"],
        "content": data["content"],
        "author": author,
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

    if all(
        query is None
        for query in (search_query, title_query, content_query)
    ):
        return jsonify(posts)

    matches = [
        post for post in posts
        if (
            search_query is not None
            and any(
                search_query.lower() in post[field].lower()
                for field in ("title", "content", "author", "date")
            )
        ) or (
            title_query is not None
            and title_query.lower() in post["title"].lower()
        ) or (
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
        (item for item in posts if item["id"] == post_id),
        None,
    )

    if post is None:
        return jsonify({
            "error": f"Beitrag mit der ID {post_id} wurde nicht gefunden."
        }), 404

    posts.remove(post)
    save_posts(posts)

    return jsonify({
        "message": f"Post with id {post_id} has been deleted successfully."
    }), 200


@app.route("/api/posts/<int:post_id>", methods=["PUT"])
def update_post(post_id):
    """Aktualisiert einen Beitrag und speichert die Änderung."""
    posts = load_posts()
    post = next(
        (item for item in posts if item["id"] == post_id),
        None,
    )

    if post is None:
        return jsonify({
            "error": f"Beitrag mit der ID {post_id} wurde nicht gefunden."
        }), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Ein JSON-Objekt wird erwartet."}), 400

    for field in ("title", "content", "author"):
        if field in data and not isinstance(data[field], str):
            return jsonify({
                "error": f"{field} muss Text sein."
            }), 400

    if "date" in data and not valid_date(data["date"]):
        return jsonify({
            "error": "Datum muss im Format YYYY-MM-DD sein."
        }), 400

    for field in ("title", "content", "author", "date"):
        if field in data:
            post[field] = data[field]

    save_posts(posts)
    return jsonify(post), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)