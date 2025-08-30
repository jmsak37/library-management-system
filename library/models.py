from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL

class Author(models.Model):
    name = models.CharField(max_length=255)
    birth_date = models.DateField(null=True, blank=True)
    biography = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Book(models.Model):
    title = models.CharField(max_length=255)
    isbn = models.CharField(max_length=20, unique=True)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")
    publication_year = models.IntegerField(null=True, blank=True)
    copies_available = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.title} ({self.isbn})"

class Borrow(models.Model):
    STATUS_CHOICES = (
        ("BORROWED", "Borrowed"),
        ("RETURNED", "Returned"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="borrows")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="borrows")
    borrow_date = models.DateTimeField(auto_now_add=True)
    return_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="BORROWED")

    class Meta:
        # prevent duplicate active borrow for same user+book
        unique_together = ("user", "book", "status")

    def __str__(self):
        return f"{self.user} -> {self.book} ({self.status})"
