from decimal import Decimal
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


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

    # new: lost fine amount (optional) - default 0.00
    lost_fine = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return f"{self.title} ({self.isbn})"


class Borrow(models.Model):
    # status values are lowercase strings — match views/serializers that check these exact values
    STATUS_BORROWED = "borrowed"
    STATUS_RETURNED = "returned"
    STATUS_LOST = "lost"

    STATUS_CHOICES = (
        (STATUS_BORROWED, "Borrowed"),
        (STATUS_RETURNED, "Returned"),
        (STATUS_LOST, "Lost"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="borrows")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="borrows")
    borrow_date = models.DateTimeField(default=timezone.now)
    return_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_BORROWED)

    # fields to support "lost book" + fine workflow
    fine_due = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    fine_paid = models.BooleanField(default=False)

    class Meta:
        # Prevent duplicate active borrow entries for the same user+book+status.
        # This allows one BORROWED record per user-book (and later a RETURNED record).
        unique_together = ("user", "book", "status")
        ordering = ("-borrow_date",)

    def __str__(self):
        return f"{self.user} -> {self.book} ({self.status})"

    def save(self, *args, **kwargs):
        """
        Ensure that when a Borrow transitions into 'returned' we increment the book copy count,
        set return_date (if missing), and clear the fine. This is intentionally minimal:
        - Only acts when status changes from something other than 'returned' to 'returned'.
        - Does NOT automatically decrement copies on creation because your views already
          handle decrementing when creating borrows (avoids double-decrement).
        """
        # determine previous status (if exists)
        old_status = None
        if self.pk:
            try:
                old = Borrow.objects.select_related('book').get(pk=self.pk)
                old_status = old.status
            except Borrow.DoesNotExist:
                old_status = None

        # If transitioning from non-returned -> returned, handle copy restoration & fine clearing
        if old_status != self.STATUS_RETURNED and self.status == self.STATUS_RETURNED:
            with transaction.atomic():
                # mark return_date if not set
                if not self.return_date:
                    self.return_date = timezone.now()
                # clear fine and mark paid
                try:
                    # ensure Decimal typed
                    self.fine_due = Decimal("0.00")
                    self.fine_paid = True
                except Exception:
                    self.fine_due = Decimal("0.00")
                    self.fine_paid = True

                # increment book copies (use select_for_update to avoid race conditions)
                # note: book is required on Borrow so assume self.book is present
                book = Book.objects.select_for_update().get(pk=self.book_id)
                # avoid integer overflow issues; cast to int and add
                book.copies_available = (book.copies_available or 0) + 1
                book.save()
                # now save the borrow record (with updated fields)
                super().save(*args, **kwargs)
                return

        # default save path (no special transition)
        super().save(*args, **kwargs)


class Claim(models.Model):
    TYPE_SAW = "saw"
    TYPE_RETURNED = "returned"
    TYPE_CHOICES = (
        (TYPE_SAW, "Saw"),
        (TYPE_RETURNED, "Returned"),
    )

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_DECLINED = "declined"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_DECLINED, "Declined"),
    )

    borrow = models.ForeignKey(Borrow, on_delete=models.CASCADE, related_name="claims")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="claims")
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_claims")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # message from user (optional) and optional offered_amount for partial payments
    message = models.TextField(blank=True)
    offered_amount = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Claim {self.id} ({self.type}) on borrow {self.borrow_id} by {self.user}"


# --- New models to support admin features and anonymous chat ---


class UserStatus(models.Model):
    """
    Lightweight 1:1 model to track whether a user is online/blocked and last seen time.
    This avoids changing your AUTH_USER_MODEL directly.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="status")
    is_online = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    last_seen = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Status for {self.user} (online={self.is_online}, blocked={self.is_blocked})"


class SupportMessage(models.Model):
    """
    Public support/chat message model. Allows anonymous or authenticated users to
    send messages to admins even when not logged-in (frontend can use this).
    """
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    def __str__(self):
        return f"SupportMessage #{self.pk} from {self.name or 'anonymous'}"
