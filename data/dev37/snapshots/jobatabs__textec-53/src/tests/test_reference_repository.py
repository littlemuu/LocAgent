import unittest
from app import app
from db_helper import reset_db, setup_db


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
        self.data = {
            "author": "Author A",
            "title": "Title A",
            "year": "2021"
        }

    def test_create_article_reference_successful(self):
        self.data['type'] = "article"
        self.data['journal'] = "Journal A"
        self.data['volume'] = "50"
        self.data['number'] = "1"
        response = self.client.post(
            "/create",
            data=self.data,
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Successfully added reference Title A.", response.data)

        response = self.client.get("/")
        self.assertIn(b"Author A", response.data)
        self.assertIn(b"Title A", response.data)
        self.assertIn(b"Journal A", response.data)
        self.assertIn(b"2021", response.data)
        self.assertIn(b"50", response.data)
        self.assertIn(b"1", response.data)

    def test_create_misc_reference_successful(self):
        self.data['type'] = "misc"
        self.data['howpublished'] = "Web"
        self.data['note'] = "Suomennettu 2001"
        response = self.client.post(
            "/create",
            data=self.data,
            follow_redirects=True
        )

        response = self.client.get("/")
        self.assertIn(b"Author A", response.data)
        self.assertIn(b"Title A", response.data)
        self.assertIn(b"2021", response.data)
        self.assertIn(b"Web", response.data)
        self.assertIn(b"Suomennettu 2001", response.data)

    def test_create_book_reference_successful(self):
        self.data['type'] = "book"
        self.data['publisher'] = "Kustantaja Oy"
        response = self.client.post(
            "/create",
            data=self.data,
            follow_redirects=True
        )

        response = self.client.get("/")
        self.assertIn(b"Author A", response.data)
        self.assertIn(b"Title A", response.data)
        self.assertIn(b"2021", response.data)
        self.assertIn(b"Kustantaja Oy", response.data)

    def test_create_reference_with_pp_successful(self):
        self.data['type'] = "article"
        self.data['journal'] = "Journal A"
        self.data['pp'] = "213-250"
        response = self.client.post(
            "/create",
            data=self.data,
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Successfully added reference Title A.", response.data)

        response = self.client.get("/")
        self.assertIn(b"Author A", response.data)
        self.assertIn(b"Title A", response.data)
        self.assertIn(b"Journal A", response.data)
        self.assertIn(b"2021", response.data)
        self.assertIn(b"pp. 213-250", response.data)

    def test_create_reference_invalid_year(self):
        self.data['type'] = "article"
        self.data['year'] = "not_a_year"
        response = self.client.post(
            "/create",
            data=self.data,
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Adding was unsuccessful. Invalid year.", response.data)

        response = self.client.get("/")
        self.assertNotIn(b"Author A", response.data)

    def test_create_reference_invalid_pp(self):
        self.data['type'] = "article"
        self.data['pp'] = "kaksisataa"
        response = self.client.post(
            "/create",
            data=self.data,
            follow_redirects=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Adding was unsuccessful. Invalid pages pertinent", response.data)

        response = self.client.get("/")
        self.assertNotIn(b"Author A", response.data)

    def test_create_reference_negative_year(self):
        self.data['type'] = "article"
        self.data['year'] = "-1"
        response = self.client.post(
            "/create",
            data=self.data,
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Adding was unsuccessful. Invalid year.", response.data)

        response = self.client.get("/")
        self.assertNotIn(b"Author A", response.data)

    def test_create_empty_reference(self):
        response = self.client.post("/create",
                                    data={},
                                    follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Adding was unsuccessful. All required fields need to be filled.", response.data)

    def test_new_post_route(self):
        type = "article"

        response = self.client.post(
            "/new",
            data=type,
            follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
