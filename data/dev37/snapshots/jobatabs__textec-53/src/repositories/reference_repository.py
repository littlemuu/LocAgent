from sqlalchemy import text
from config import db
from entities.reference import Reference


def get_references():
    result = db.session.execute(
        text("SELECT id, type, author, title, year, journal, volume, \
             number, publisher, howpublished, note, pp FROM reference_items"))
    rows = result.fetchall()
    references_list = [
        Reference(
            _id=row[0],
            category=row[1],
            author=row[2],
            title=row[3],
            year=row[4],
            journal=row[5],
            volume=row[6],
            number=row[7],
            publisher=row[8],
            howpublished=row[9],
            note=row[10],
            pp=row[11],
        )
        for row in rows
    ]
    return references_list


def delete_reference(_id):
    sql = text("DELETE FROM reference_items WHERE id=:id")
    db.session.execute(sql, {"id": _id})
    db.session.commit()


def create_reference(references: dict):  # toimiiko???
    filtered_references = {key: value for key,
                           value in references.items() if value is not None}

    keys = ", ".join(filtered_references.keys())
    values = ", ".join(f":{key}" for key in filtered_references.keys())

    sql = text(f"INSERT INTO reference_items ({keys}) VALUES ({values})")

    db.session.execute(sql, filtered_references)
    db.session.commit()


def get_title(_id):
    sql = text("SELECT title FROM reference_items WHERE id = :id")
    result = db.session.execute(sql, {"id": _id}).fetchone()
    if result:
        return result[0]
    return None


def get_reference_by_id(reference_id):
    sql = text("""
        SELECT id, type, author, title, year, journal, volume, number, publisher, howpublished, note, pp
        FROM reference_items
        WHERE id = :id
    """)
    result = db.session.execute(sql, {"id": reference_id}).fetchone()
    if result:
        return Reference(
            _id=result[0],
            category=result[1],
            author=result[2],
            title=result[3],
            year=result[4],
            journal=result[5],
            volume=result[6],
            number=result[7],
            publisher=result[8],
            howpublished=result[9],
            note=result[10],
            pp=result[11],
        )
    return None


def update_reference(reference_id, updated_data):
    sql = text("""
        UPDATE reference_items
        SET author = :author, title = :title, year = :year, journal = :journal,
            volume = :volume, number = :number, publisher = :publisher,
            howpublished = :howpublished, note = :note, pp = :pp
        WHERE id = :id
    """)
    updated_data["id"] = reference_id

    db.session.execute(sql, updated_data)
    db.session.commit()
