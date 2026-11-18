import unittest
from unittest.mock import patch
from sqlalchemy.exc import SQLAlchemyError
from app import app
from db_helper import reset_db, setup_db


class TestDeleteReferenceRoutes(unittest.TestCase):
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
                "author": "Author A",
                "title": "Title A",
                "year": "2021",
                "journal": "Journal A"
            },
            follow_redirects=True
        )

    def test_delete_reference_successful(self):
        response = self.client.post("/delete/2", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Successfully deleted reference Title A.", response.data)

        response = self.client.get("/")
        self.assertNotIn(b"Title A", response.data)
        self.assertNotIn(b"Author A", response.data)

    def test_delete_reference_not_found(self):
        response = self.client.post("/delete/999", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"The reference could not be deleted.", response.data)

    def test_get_request_to_delete_endpoint(self):
        response = self.client.get("/delete/1", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"GET requests are not allowed for deletion.", response.data)

        response = self.client.get("/")
        self.assertIn(b"Title A", response.data)
        self.assertIn(b"Author A", response.data)


class TestDeleteReferenceExceptionHandling(unittest.TestCase):
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

    def test_delete_reference_sqlalchemy_error(self):
        with patch("repositories.reference_repository.delete_reference") as mock_delete:
            mock_delete.side_effect = SQLAlchemyError("Test database error")

            response = self.client.post(
                "/delete/invalid_id", follow_redirects=True)

            self.assertEqual(response.status_code, 500)


if __name__ == "__main__":
    unittest.main()
