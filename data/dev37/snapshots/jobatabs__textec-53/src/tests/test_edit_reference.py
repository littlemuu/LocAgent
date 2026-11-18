import unittest
from app import app
from db_helper import reset_db, setup_db
from sqlalchemy.exc import SQLAlchemyError


class TestReferenceRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app_context = app.app_context()
        cls.app_context.push()

        setup_db()

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def setUp(self):
        reset_db()
        self.client = app.test_client()

        self.client.post(
            "/create",
            data={
                "type": "article",
                "author": "Allan Collins",
                "title": "Visible Thinking",
                "year": "1991",
                "journal": "Educational Research",
                "volume": "50",
                "number": "2"
            },
            follow_redirects=True
        )

    def tearDown(self):
        pass

    def test_1_edit_reference_success(self):
        response = self.client.post(
            "/edit/1",
            data={
                "author": "Rune Klevjer",
                "title": "In defense of cutscenes",
                "year": "2002",
                "journal": "Game Studies",
                "volume": "50",
                "number": "2"
            },
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Successfully updated reference", response.data)

        response = self.client.get("/")
        print(response.data.decode())  # debug

        self.assertIn(b"Rune Klevjer", response.data)
        self.assertIn(b"In defense of cutscenes", response.data)
        self.assertIn(b"Game Studies", response.data)
        self.assertIn(b"2002", response.data)
        self.assertIn(b"vol. 50, no. 2", response.data)

    def test_2_edit_reference_failure_invalid_year(self):
        response = self.client.post(
            "/edit/1",
            data={
                "author": "Rune Klevjer",
                "title": "In defense of cutscenes",
                "year": "-1",  # invalid year
                "journal": "Game Studies",
                "volume": "50",
                "number": "2"
            },
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        response = self.client.get("/")
        self.assertIn(b"Allan Collins", response.data)
        self.assertIn(b"Visible Thinking", response.data)
        self.assertIn(b"1991", response.data)
