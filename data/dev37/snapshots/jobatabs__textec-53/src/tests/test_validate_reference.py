import unittest
from util import validate_reference, UserInputError


class TestValidateReference(unittest.TestCase):
    def test_valid_pp_and_year(self):
        raised = False
        data = {
            "type": "article",
            "author": "Mikko Mallikainen",
            "title": "Artikkeli",
            "year": "2001",
            "journal": "Lehti",
            "pp": "213"
        }
        try:
            validate_reference(data)
        except UserInputError:
            raised = True
        self.assertFalse(raised)

    def test_valid_pp_range(self):
        raised = False
        data = {
            "type": "article",
            "author": "Mikko Mallikainen",
            "title": "Artikkeli",
            "year": "2001",
            "journal": "Lehti",
            "pp": "213-250"
        }
        try:
            validate_reference(data)
        except UserInputError:
            raised = True
        self.assertFalse(raised)

    def test_invalid_pp(self):
        data = {
            "type": "article",
            "author": "Mikko Mallikainen",
            "title": "Artikkeli",
            "year": "2001",
            "journal": "Lehti",
            "pp": "kaksi"
        }
        self.assertRaises(UserInputError, validate_reference, data)

    def test_pp_too_long(self):
        data = {
            "type": "article",
            "author": "Mikko Mallikainen",
            "title": "Artikkeli",
            "year": "2001",
            "journal": "Lehti",
            "pp": "aivanliianpitkä, siis naurettavan pitkä, aivan todella pitkä merkkijono"
        }
        self.assertRaises(UserInputError, validate_reference, data)

    def test_invalid_year(self):
        data = {
            "type": "article",
            "author": "Mikko Mallikainen",
            "title": "Artikkeli",
            "year": "kaksituhattayksi",
            "journal": "Lehti",
            "pp": "213"
        }
        self.assertRaises(UserInputError, validate_reference, data)

    def test_year_too_small(self):
        data = {
            "type": "article",
            "author": "Mikko Mallikainen",
            "title": "Artikkeli",
            "year": "1000",
        }
        self.assertRaises(UserInputError, validate_reference, data)
