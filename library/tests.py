# library/tests.py
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Author, Book, Borrow
from django.utils import timezone

User = get_user_model()


class TestBorrowCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="bob", password="pass123")
        self.author = Author.objects.create(name="Author A")
        self.book = Book.objects.create(title="B", isbn="isbn1", author=self.author, copies_available=1)

    def authenticate(self, user=None):
        """Helper to authenticate the test client (defaults to self.user)."""
        if user is None:
            user = self.user
        self.client.force_authenticate(user=user)

    def unauthenticate(self):
        """Helper to remove authentication from the test client."""
        self.client.force_authenticate(user=None)

    def test_borrow_and_return(self):
        # Authenticate user
        self.authenticate()

        # Borrow the book
        resp = self.client.post("/api/borrow/", {"book_id": self.book.id}, format="json")
        self.assertEqual(resp.status_code, 201, msg=f"Borrow failed: {resp.status_code} {resp.data}")
        self.book.refresh_from_db()
        self.assertEqual(self.book.copies_available, 0)

        borrow_id = resp.data["id"]

        # Return the book
        resp2 = self.client.post("/api/return/", {"borrow_id": borrow_id}, format="json")
        self.assertEqual(resp2.status_code, 200, msg=f"Return failed: {resp2.status_code} {resp2.data}")
        self.book.refresh_from_db()
        self.assertEqual(self.book.copies_available, 1)

    def test_borrow_when_no_copies(self):
        self.authenticate()
        # reduce copies to 0
        self.book.copies_available = 0
        self.book.save()
        resp = self.client.post("/api/borrow/", {"book_id": self.book.id}, format="json")
        self.assertEqual(resp.status_code, 400)
        # message should mention no copies (case-insensitive)
        self.assertIn("no copies available", str(resp.data).lower())

    def test_double_borrow(self):
        self.authenticate()
        resp1 = self.client.post("/api/borrow/", {"book_id": self.book.id}, format="json")
        self.assertEqual(resp1.status_code, 201)
        # try to borrow again
        resp2 = self.client.post("/api/borrow/", {"book_id": self.book.id}, format="json")
        self.assertEqual(resp2.status_code, 400)
        # message should indicate an existing/active borrow (robust check)
        msg = str(resp2.data).lower()
        self.assertTrue(("already" in msg) or ("active borrow" in msg) or ("already borrowed" in msg),
                        msg=f"Unexpected message for double borrow: {resp2.data}")

    def test_borrow_invalid_request_missing_book_id(self):
        self.authenticate()
        resp = self.client.post("/api/borrow/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("book_id is required", str(resp.data).lower())

    def test_return_already_returned(self):
        self.authenticate()
        # create borrow
        resp = self.client.post("/api/borrow/", {"book_id": self.book.id}, format="json")
        self.assertEqual(resp.status_code, 201)
        borrow_id = resp.data["id"]
        # return
        resp2 = self.client.post("/api/return/", {"borrow_id": borrow_id}, format="json")
        self.assertEqual(resp2.status_code, 200)
        # return again should fail
        resp3 = self.client.post("/api/return/", {"borrow_id": borrow_id}, format="json")
        self.assertEqual(resp3.status_code, 400)
        self.assertIn("already returned", str(resp3.data).lower())
