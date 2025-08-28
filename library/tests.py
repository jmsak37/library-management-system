# library/tests.py
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Author, Book
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Author, Book, Borrow
from django.utils import timezone

User = get_user_model()

class BorrowTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="bob", password="pass123")
        self.author = Author.objects.create(name="Author A")
        self.book = Book.objects.create(title="B", isbn="isbn1", author=self.author, copies_available=1)

    def test_borrow_and_return(self):
        # Use DRF's force_authenticate so the client is authenticated for JWT-only setups
        self.client.force_authenticate(user=self.user)

        # Borrow the book
        resp = self.client.post("/api/borrow/", {"book_id": self.book.id}, format='json')
        self.assertEqual(resp.status_code, 201, msg=f"Borrow failed: {resp.status_code} {resp.data}")
        self.book.refresh_from_db()
        self.assertEqual(self.book.copies_available, 0)

        borrow_id = resp.data["id"]
        resp2 = self.client.post("/api/return/", {"borrow_id": borrow_id}, format='json')
        self.assertEqual(resp2.status_code, 200, msg=f"Return failed: {resp2.status_code} {resp2.data}")
        self.book.refresh_from_db()
        self.assertEqual(self.book.copies_available, 1)

    def test_borrow_when_no_copies(self):
        self.authenticate()
        # reduce copies to 0
        self.book.copies_available = 0
        self.book.save()
        resp = self.client.post("/api/borrow/", {"book_id": self.book.id}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No copies available", str(resp.data))

    def test_double_borrow(self):
        self.authenticate()
        resp1 = self.client.post("/api/borrow/", {"book_id": self.book.id}, format='json')
        self.assertEqual(resp1.status_code, 201)
        # try to borrow again
        resp2 = self.client.post("/api/borrow/", {"book_id": self.book.id}, format='json')
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("already have an active borrow", str(resp2.data))

    def test_borrow_invalid_request_missing_book_id(self):
        self.authenticate()
        resp = self.client.post("/api/borrow/", {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("book_id is required", str(resp.data))


    def test_return_already_returned(self):
        self.authenticate()
        # create borrow
        resp = self.client.post("/api/borrow/", {"book_id": self.book.id}, format='json')
        self.assertEqual(resp.status_code, 201)
        borrow_id = resp.data["id"]
        # return
        resp2 = self.client.post("/api/return/", {"borrow_id": borrow_id}, format='json')
        self.assertEqual(resp2.status_code, 200)
        # return again should fail
        resp3 = self.client.post("/api/return/", {"borrow_id": borrow_id}, format='json')
        self.assertEqual(resp3.status_code, 400)
        self.assertIn("already returned", str(resp3.data))