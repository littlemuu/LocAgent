class Reference:
    def __init__(self, _id: int, category, author, title, year, journal=None,
                 volume=None, number=None, publisher=None, howpublished=None, note=None, pp=None):
        # __tablename__ = "reference_items"
        self.reference = {
            "id": _id,
            "type": category,
            "author": author,
            "title": title,
            "year": year,
            "journal": journal,
            "volume": volume,
            "number": number,
            "pp": pp,
            "publisher": publisher,
            "howpublished": howpublished,
            "note": note
        }

    @classmethod
    def get_fields(cls, reference_type):
        fields = ["author", "title", "year"]
        if reference_type == 'article':
            fields.extend(['journal', 'pp', 'volume', 'number'])
        elif reference_type == 'book':
            fields.extend(['publisher', 'pp'])
        else:  # type=misc
            fields.extend(['howpublished', 'note', 'pp'])

        return fields

    def __str__(self):
        output = []
        fields_for_type = self.__class__.get_fields(self.reference['type'])
        fields_for_type.remove("year")
        fields_for_type.append("year")
        for field in fields_for_type:
            value = self.reference.get(field)
            if value is not None:
                if field == "journal" and "pp" in fields_for_type \
                        and self.reference.get("pp") is not None:
                    output.append(f"{str(value)} ")
                elif field == "pp":
                    output.append(f"(pp. {value}), ")
                elif field == "volume":
                    output.append(f"vol. {value}, ")
                elif field == "number":
                    output.append(f"no. {value}, ")
                else:
                    output.append(f"{str(value)}, ")

        return "".join(output)[:-2]


if __name__ == "__main__":  # pragma: no cover
    # tämä toimii
    test = Reference(1, 'article', 'Orange Cat', 'How to Dominate The world',
                     '2005', 'Cat Chronicles', pp='200-300')
    test2 = Reference(2, 'book', 'Black Cat', 'How to Jump',
                      '2024', publisher='Brother')
    print(test)
    print(test2)
