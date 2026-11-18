from flask import redirect, render_template, request, jsonify, flash, send_file
from sqlalchemy.exc import SQLAlchemyError
from db_helper import reset_db
from repositories.reference_repository import (
    get_references, create_reference, delete_reference, get_title,
    get_reference_by_id, update_reference
)
from config import app, test_env
from util import validate_reference, UserInputError
from bib_generator import create_bibfile
from entities.reference import Reference


@app.route("/")
def index():
    references = get_references()
    return render_template("index.html", references=references)


@app.route("/new", methods=["GET", "POST"])
def new():
    selected_type = request.form.get("type")
    fields = Reference.get_fields(selected_type)
    return render_template("new.html", fields=fields,
                           required=["author", "title", "year"], type=selected_type)


@app.route("/create", methods=["POST"])
def creation():
    inputs = ["author", "title", "year", "journal", "volume",
              "number", "publisher", "howpublished", "note", "pp"]
    reference_dict = {input: request.form.get(input) if request.form.get(
        input) != "" else None for input in inputs}
    selected_type = request.form.get("type")
    reference_dict["type"] = selected_type

    try:
        validate_reference(reference_dict)
        create_reference(reference_dict)
        flash(
            f"Successfully added reference {reference_dict['title']}.", 'success')
        return redirect("/")
    except UserInputError as error:
        flash(str(error), 'error')
        fields = Reference.get_fields(selected_type)
        return render_template("new.html", fields=fields,
                               required=["author", "title", "year"], type=selected_type)


@app.route("/delete/<reference_id>", methods=["POST"])
def delete(reference_id):
    try:
        title = get_title(reference_id)
        if title:
            delete_reference(reference_id)
            flash(f"Successfully deleted reference {title}.", "success")
        else:
            flash("The reference could not be deleted.", "error")
    except SQLAlchemyError:
        flash("The reference could not be deleted.", "error")
    return redirect("/")


@app.route("/delete/<reference_id>", methods=["GET"])
def handle_get_delete(reference_id):  # pylint: disable=unused-argument
    flash("GET requests are not allowed for deletion.", "error")
    return redirect("/")


@app.route("/edit/<reference_id>", methods=["GET"])
def edit(reference_id):
    reference = get_reference_by_id(reference_id)

    if not reference:
        flash("Reference not found.", "error")
        return redirect("/")

    fields = Reference.get_fields(reference.reference["type"])

    return render_template(
        "edit.html",
        reference=reference.reference,
        fields=fields,
        required=["author", "title", "year"],
    )


@app.route("/edit/<reference_id>", methods=["POST"])
def update_reference_route(reference_id):
    inputs = ["author", "title", "year", "journal", "volume",
              "number", "publisher", "howpublished", "note", "pp"]
    updated_data = {input: request.form.get(input) if request.form.get(
        input) != "" else None for input in inputs}

    try:
        update_reference(reference_id, updated_data)
        flash(
            f"Successfully updated reference {updated_data['title']}.", "success")
    except SQLAlchemyError:
        flash("An error occurred while updating the reference.", "error")

    return redirect("/")


@app.route("/export_bibtex_file")
def export_bibtex_file():
    references = get_references()
    create_bibfile(references)

    return send_file("../references.bib", as_attachment=True, download_name="references.bib")


# testausta varten oleva reitti
if test_env:
    @app.route("/reset_db")
    def reset_database():
        reset_db()
        return jsonify({'message': "db reset"})
