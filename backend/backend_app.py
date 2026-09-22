from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint


app = Flask(__name__)

CORS(app)

SWAGGER_URL = "/api/docs"
API_URL = "/static/masterblog.json"

swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={"app_name": "Masterblog API"},
)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)



POSTS = [
    {"id": 1, "title": "First post", "content": "This is the first post."},
    {"id": 2, "title": "Second post", "content": "This is the second post."},
]

# Die nächste ID wird bei jedem neuen Beitrag erhöht.
# Dadurch wird eine gelöschte ID nicht erneut vergeben.
next_post_id = max((post["id"] for post in POSTS), default=0) + 1


@app.route("/api/posts", methods=["GET"])
def get_posts():
    """Gibt Beiträge optional sortiert zurück."""
    sort_field = request.args.get("sort")
    direction = request.args.get("direction", "asc")

    if sort_field is not None and sort_field not in ("title", "content"):
        return jsonify({
            "error": "Ungültiges Sortierfeld. Erlaubt sind title und content."
        }), 400

    if direction not in ("asc", "desc"):
        return jsonify({
            "error": "Ungültige Sortierrichtung. Erlaubt sind asc und desc."
        }), 400

    # Ohne Sortierfeld bleibt die ursprüngliche Reihenfolge erhalten.
    if sort_field is None:
        return jsonify(POSTS)

    # sorted() erstellt eine neue Liste und verändert POSTS nicht.
    sorted_posts = sorted(
        POSTS,
        key=lambda post: post[sort_field].lower(),
        reverse=(direction == "desc"),
    )
    return jsonify(sorted_posts)


@app.route("/api/posts", methods=["POST"])
def add_post():
    """Erstellt einen neuen Beitrag."""
    global next_post_id

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

    new_post = {
        "id": next_post_id,
        "title": data["title"],
        "content": data["content"],
    }
    POSTS.append(new_post)
    next_post_id += 1

    return jsonify(new_post), 201


@app.route("/api/posts/search", methods=["GET"])
def search_posts():
    """Sucht Beiträge anhand ihres Titels oder Inhalts."""
    title_query = request.args.get("title")
    content_query = request.args.get("content")

    # Ohne Suchparameter alle Beiträge zurückgeben.
    if title_query is None and content_query is None:
        return jsonify(POSTS)

    # Ein Treffer in einem der angegebenen Felder reicht aus.
    matches = [
        post for post in POSTS
        if (
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
    """Löscht einen Beitrag anhand seiner ID."""
    for post in POSTS:
        if post["id"] == post_id:
            POSTS.remove(post)
            return jsonify({
                "message": (
                    f"Post with id {post_id} has been deleted successfully."
                )
            }), 200

    return jsonify({
        "error": f"Beitrag mit der ID {post_id} wurde nicht gefunden."
    }), 404


@app.route("/api/posts/<int:post_id>", methods=["PUT"])
def update_post(post_id):
    """Aktualisiert die übermittelten Felder eines Beitrags."""
    post = next(
        (item for item in POSTS if item["id"] == post_id),
        None,
    )

    if post is None:
        return jsonify({
            "error": f"Beitrag mit der ID {post_id} wurde nicht gefunden."
        }), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Ein JSON-Objekt wird erwartet."}), 400

    # Nicht übermittelte Felder behalten ihre bisherigen Werte.
    if "title" in data:
        post["title"] = data["title"]
    if "content" in data:
        post["content"] = data["content"]

    return jsonify(post), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)