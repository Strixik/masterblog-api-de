"use strict";

const baseUrlInput = document.getElementById("api-base-url");
const messageElement = document.getElementById("message");
const postContainer = document.getElementById("post-container");
const emptyState = document.getElementById("empty-state");
const postCount = document.getElementById("post-count");

const postForm = document.getElementById("post-form");
const editorHeading = document.getElementById("editor-heading");
const submitButton = document.getElementById("submit-button");
const cancelEditButton = document.getElementById("cancel-edit-button");

const titleInput = document.getElementById("post-title");
const contentInput = document.getElementById("post-content");
const authorInput = document.getElementById("post-author");
const dateInput = document.getElementById("post-date");

const searchInput = document.getElementById("search-input");
const sortFieldInput = document.getElementById("sort-field");
const sortDirectionInput = document.getElementById("sort-direction");

let editingPostId = null;
let displayedPosts = [];


function getBaseUrl() {
    return baseUrlInput.value.trim().replace(/\/+$/, "");
}


function showMessage(text, type = "error") {
    messageElement.textContent = text;
    messageElement.className = `message ${type}`;
    messageElement.hidden = false;
}


function clearMessage() {
    messageElement.textContent = "";
    messageElement.hidden = true;
}


async function apiRequest(path, options = {}) {
    const baseUrl = getBaseUrl();

    if (!baseUrl) {
        throw new Error("Bitte zuerst die API Base URL eingeben.");
    }

    localStorage.setItem("apiBaseUrl", baseUrl);

    let response;

    try {
        response = await fetch(`${baseUrl}${path}`, options);
    } catch {
        throw new Error(
            "Die API ist nicht erreichbar. Bitte URL und Backend prüfen."
        );
    }

    let data;

    try {
        data = await response.json();
    } catch {
        throw new Error(`Die API hat keine gültige JSON-Antwort gesendet (${response.status}).`);
    }

    if (!response.ok) {
        let detail = data.error || data.message || `HTTP ${response.status}`;

        if (Array.isArray(data.fields) && data.fields.length > 0) {
            detail += ` Fehlende Felder: ${data.fields.join(", ")}.`;
        }

        throw new Error(detail);
    }

    return data;
}


function createButton(label, className, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
}


function renderPosts(posts) {
    displayedPosts = posts;
    postContainer.replaceChildren();

    postCount.textContent = `${posts.length} ${
        posts.length === 1 ? "Beitrag" : "Beiträge"
    }`;
    emptyState.hidden = posts.length !== 0;

    for (const post of posts) {
        const article = document.createElement("article");
        article.className = "post";

        const header = document.createElement("div");
        header.className = "post-header";

        const heading = document.createElement("h3");
        heading.textContent = post.title;

        const actions = document.createElement("div");
        actions.className = "post-actions";
        actions.append(
            createButton("Bearbeiten", "button small secondary", () => {
                startEditing(post);
            }),
            createButton("Löschen", "button small danger", () => {
                deletePost(post.id);
            })
        );

        header.append(heading, actions);

        const metadata = document.createElement("p");
        metadata.className = "post-meta";
        metadata.textContent =
            `${post.author || "Unbekannt"} · ${post.date || "Kein Datum"} · #${post.id}`;

        const content = document.createElement("p");
        content.className = "post-content";
        content.textContent = post.content;

        article.append(header, metadata, content);
        postContainer.appendChild(article);
    }
}


async function loadPosts() {
    clearMessage();

    const search = searchInput.value.trim();
    const sort = sortFieldInput.value;
    const direction = sortDirectionInput.value;

    const params = new URLSearchParams();
    let path = "/posts";

    if (search) {
        // Der Such-Endpunkt unterstützt keine Sortierparameter.
        path = "/posts/search";
        params.set("search", search);
    } else if (sort) {
        params.set("sort", sort);
        params.set("direction", direction);
    }

    if (params.size > 0) {
        path += `?${params.toString()}`;
    }

    try {
        let posts = await apiRequest(path);

        // Bei aktiver Suche sortiert das Frontend die Suchergebnisse.
        if (search && sort) {
            posts = [...posts].sort((a, b) => {
                const comparison = sort === "date"
                    ? a.date.localeCompare(b.date)
                    : a[sort].localeCompare(b[sort], undefined, {
                        sensitivity: "base"
                    });

                return direction === "desc" ? -comparison : comparison;
            });
        }

        renderPosts(posts);
    } catch (error) {
        showMessage(error.message);
    }
}


function resetEditor() {
    editingPostId = null;
    postForm.reset();
    editorHeading.textContent = "Neuen Beitrag schreiben";
    submitButton.textContent = "Beitrag erstellen";
    cancelEditButton.hidden = true;
}


function startEditing(post) {
    editingPostId = post.id;
    titleInput.value = post.title;
    contentInput.value = post.content;
    authorInput.value = post.author || "";
    dateInput.value = post.date || "";

    editorHeading.textContent = `Beitrag #${post.id} bearbeiten`;
    submitButton.textContent = "Änderungen speichern";
    cancelEditButton.hidden = false;

    postForm.scrollIntoView({ behavior: "smooth", block: "start" });
    titleInput.focus();
}


async function savePost(event) {
    event.preventDefault();
    clearMessage();

    const title = titleInput.value.trim();
    const content = contentInput.value.trim();
    const author = authorInput.value.trim();
    const postDate = dateInput.value;

    if (!title || !content) {
        showMessage("Titel und Inhalt dürfen nicht leer sein.");
        return;
    }

    const payload = { title, content };

    if (author) {
        payload.author = author;
    } else if (editingPostId !== null) {
        payload.author = "Unbekannt";
    }

    if (postDate) {
        payload.date = postDate;
    }

    const isEditing = editingPostId !== null;
    const path = isEditing ? `/posts/${editingPostId}` : "/posts";

    submitButton.disabled = true;

    try {
        await apiRequest(path, {
            method: isEditing ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        resetEditor();
        await loadPosts();
        showMessage(
            isEditing ? "Beitrag aktualisiert." : "Beitrag erstellt.",
            "success"
        );
    } catch (error) {
        showMessage(error.message);
    } finally {
        submitButton.disabled = false;
    }
}


const deleteDialog = document.getElementById("delete-dialog");
const confirmDeleteButton = document.getElementById("confirm-delete-button");
const cancelDeleteButton = document.getElementById("cancel-delete-button");

let postIdToDelete = null;

function deletePost(postId) {
    postIdToDelete = postId;
    deleteDialog.showModal();
}

cancelDeleteButton.addEventListener("click", () => {
    deleteDialog.close();
});

deleteDialog.addEventListener("close", () => {
    postIdToDelete = null;
});

confirmDeleteButton.addEventListener("click", async () => {
    const postId = postIdToDelete;

    if (postId === null) {
        return;
    }

    confirmDeleteButton.disabled = true;
    clearMessage();

    try {
        await apiRequest(`/posts/${postId}`, { method: "DELETE" });
        deleteDialog.close();

        if (editingPostId === postId) {
            resetEditor();
        }

        await loadPosts();
        showMessage("Beitrag gelöscht.", "success");
    } catch (error) {
        deleteDialog.close();
        showMessage(error.message);
    } finally {
        confirmDeleteButton.disabled = false;
    }
});


document.getElementById("load-button").addEventListener("click", loadPosts);
document.getElementById("cancel-edit-button").addEventListener(
    "click",
    resetEditor
);
document.getElementById("reset-filter-button").addEventListener(
    "click",
    () => {
        searchInput.value = "";
        sortFieldInput.value = "";
        sortDirectionInput.value = "asc";
        loadPosts();
    }
);

document.getElementById("filter-form").addEventListener(
    "submit",
    (event) => {
        event.preventDefault();
        loadPosts();
    }
);

postForm.addEventListener("submit", savePost);

const savedBaseUrl = localStorage.getItem("apiBaseUrl");
if (savedBaseUrl) {
    baseUrlInput.value = savedBaseUrl;
}

loadPosts();