from decimal import Decimal, InvalidOperation
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from .models import Author, Book, Borrow, Claim, UserStatus, SupportMessage

User = get_user_model()


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserSerializer(serializers.ModelSerializer):
    """Lightweight user serializer for nested displays"""

    class Meta:
        model = User
        fields = ("id", "username", "email")


class UserListSerializer(serializers.ModelSerializer):
    """serializer for admin user listing (non-admin users)"""
    class Meta:
        model = User
        fields = ("id", "username", "email")


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ("id", "name", "birth_date", "biography")


class BookSerializer(serializers.ModelSerializer):
    # nested read-only author representation
    author = AuthorSerializer(read_only=True)
    # write-only foreign key field for creating/updating via author id
    author_id = serializers.PrimaryKeyRelatedField(
        source="author",
        queryset=Author.objects.all(),
        write_only=True,
        required=True,
    )

    # optional lost fine (some backends name this differently; keep as lost_fine)
    lost_fine = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, default=Decimal("0.00"))

    class Meta:
        model = Book
        fields = (
            "id",
            "title",
            "isbn",
            "author",
            "author_id",
            "publication_year",
            "copies_available",
            "lost_fine",
        )

    def validate_isbn(self, value):
        qs = Book.objects.filter(isbn=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A book with this ISBN already exists.")
        return value

    def validate_copies_available(self, value):
        if value is None:
            return value
        if value < 0:
            raise serializers.ValidationError("copies_available must be 0 or greater.")
        return value

    def validate_lost_fine(self, value):
        try:
            v = Decimal(value)
        except Exception:
            raise serializers.ValidationError("Invalid fine amount.")
        if v < 0:
            raise serializers.ValidationError("lost_fine must be 0 or greater.")
        return v

    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)


class BorrowSerializer(serializers.ModelSerializer):
    # nested display of user and book, plus write-only ids
    user = UserSerializer(read_only=True)
    book = BookSerializer(read_only=True)

    book_id = serializers.PrimaryKeyRelatedField(
        source="book",
        queryset=Book.objects.all(),
        write_only=True,
        required=False,
    )

    # allow admin to create for another user by passing username or user_id
    username = serializers.CharField(write_only=True, required=False, allow_null=True)
    user_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    # optional due_date field (write-only; your view may use it)
    due_date = serializers.DateField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Borrow
        fields = (
            "id",
            "user",
            "book",
            "book_id",
            "borrow_date",
            "return_date",
            "status",
            "fine_due",
            "fine_paid",
            "username",
            "user_id",
            "due_date",
        )
        read_only_fields = ("user", "borrow_date", "fine_due", "fine_paid")

    def validate(self, attrs):
        if self.instance is None:
            book = attrs.get("book")
            if book is None:
                raise serializers.ValidationError({"book_id": "This field is required."})
            if getattr(book, "copies_available", 0) <= 0:
                raise serializers.ValidationError({"detail": "No copies available"})
        return attrs

    def create(self, validated_data):
        request = self.context.get("request", None)
        book = validated_data.get("book")
        if book is None and request is not None:
            bid = request.data.get("book_id") or None
            if bid:
                book = Book.objects.filter(pk=bid).first()

        if book is None:
            raise serializers.ValidationError({"book_id": "Book not found or not provided."})

        target_user = None
        if request and hasattr(request, "user") and request.user.is_staff:
            username = self.initial_data.get("username") or None
            user_id = self.initial_data.get("user_id") or None
            if username:
                try:
                    target_user = User.objects.get(username=username)
                except User.DoesNotExist:
                    raise serializers.ValidationError({"username": f"User with username '{username}' not found."})
            elif user_id:
                try:
                    target_user = User.objects.get(pk=user_id)
                except User.DoesNotExist:
                    raise serializers.ValidationError({"user_id": f"User with id '{user_id}' not found."})
        if target_user is None:
            if request and hasattr(request, "user") and request.user.is_authenticated:
                target_user = request.user
            else:
                raise serializers.ValidationError({"user": "Authenticated user required."})

        active_exists = Borrow.objects.filter(user=target_user, book=book).exclude(status__iexact="returned").exists()
        if active_exists:
            raise serializers.ValidationError({"detail": "User already has an active borrow for this book."})

        if getattr(book, "copies_available", 0) <= 0:
            raise serializers.ValidationError({"detail": "No copies available"})

        with transaction.atomic():
            book.copies_available -= 1
            book.save()

            borrow = Borrow.objects.create(
                user=target_user,
                book=book,
                status=Borrow.STATUS_BORROWED if hasattr(Borrow, "STATUS_BORROWED") else "borrowed",
                fine_due=validated_data.get("fine_due", Decimal("0.00")),
                fine_paid=validated_data.get("fine_paid", False),
            )

        return borrow


class ClaimSerializer(serializers.ModelSerializer):
    """
    Serializer for Claim model.
    - Exposes read-only nested user and borrow information.
    - Accepts `borrow_id` on write to associate claim with borrow.
    - Sets `user` on create from request.user and defaults status to 'pending'.
    """
    user = UserSerializer(read_only=True)
    borrow = BorrowSerializer(read_only=True)

    borrow_id = serializers.PrimaryKeyRelatedField(
        source="borrow",
        queryset=Borrow.objects.all(),
        write_only=True,
        required=True,
    )

    # Allow offered_amount to be passed; will validate in create/field validator
    offered_amount = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Claim
        fields = ("id", "user", "borrow", "borrow_id", "type", "status", "created_at", "offered_amount", "message")
        read_only_fields = ("user", "status", "created_at")

    def validate(self, attrs):
        borrow = attrs.get("borrow")
        if borrow is None:
            raise serializers.ValidationError({"borrow_id": "This field is required."})

        # Don't allow creating claims when the borrow's fine is already paid
        if getattr(borrow, "fine_paid", False):
            raise serializers.ValidationError({"detail": "Fine already paid for this borrow; cannot submit a claim."})

        # If claim is type 'saw' ensure it's reasonable (usually for LOST borrows)
        claim_type = attrs.get("type")
        if claim_type == Claim.TYPE_SAW:
            # Allow 'saw' only when borrow is lost or at least not already returned
            if getattr(borrow, "status", "").lower() == Borrow.STATUS_RETURNED:
                raise serializers.ValidationError({"type": "Cannot submit 'saw' claim for a returned borrow."})
        return attrs

    def validate_offered_amount(self, value):
        """
        Validate offered_amount separately if present:
        - Numeric/Decimal coercion is handled by DecimalField, but extra checks here:
          * must be >= 0
          * must not exceed the current fine (use borrow.fine_due if >0 else book.lost_fine)
        """
        if value in (None, ''):
            return None
        try:
            dec = Decimal(value)
        except (InvalidOperation, TypeError):
            raise serializers.ValidationError("Invalid offered_amount")

        if dec < 0:
            raise serializers.ValidationError("offered_amount must be >= 0")

        # Try to determine borrow from initial_data to compare amounts (best-effort)
        borrow_obj = None
        bid = self.initial_data.get("borrow_id") or self.initial_data.get("borrow") or None
        if bid:
            try:
                borrow_obj = Borrow.objects.select_related("book").get(pk=bid)
            except Borrow.DoesNotExist:
                borrow_obj = None

        if borrow_obj:
            # choose base fine: borrow.fine_due if >0 else book.lost_fine
            base_fine = (borrow_obj.fine_due if (borrow_obj.fine_due and borrow_obj.fine_due > Decimal("0.00")) else (borrow_obj.book.lost_fine or Decimal("0.00")))
            try:
                base_fine = Decimal(base_fine)
            except Exception:
                base_fine = Decimal("0.00")

            if dec > base_fine:
                raise serializers.ValidationError("offered_amount cannot exceed the current fine.")

        return dec

    def create(self, validated_data):
        """
        Create the claim. We do not mutate Borrow here — admin must approve and the admin code
        (views) is responsible for applying payments, clearing fines, and marking returns.
        """

        request = self.context.get("request", None)
        user = None
        if request and hasattr(request, "user") and request.user.is_authenticated:
            user = request.user
        else:
            raise serializers.ValidationError({"user": "Authenticated user required to submit a claim."})

        # Normalise offered_amount in validated_data (ensure Decimal or None)
        offered = validated_data.get("offered_amount", None)
        if offered in (None, ''):
            validated_data['offered_amount'] = None
        else:
            # If DRF did not already coerce, attempt to coerce here
            try:
                validated_data['offered_amount'] = Decimal(offered)
            except (InvalidOperation, TypeError):
                raise serializers.ValidationError({"offered_amount": "Invalid amount."})

            if validated_data['offered_amount'] < 0:
                raise serializers.ValidationError({"offered_amount": "Must be >= 0"})

        # default status to pending (status is read-only in serializer inputs; we'll set explicitly after create)
        claim = Claim.objects.create(user=user, **validated_data)
        # ensure explicit pending status (in case model default differs)
        claim.status = Claim.STATUS_PENDING
        claim.save(update_fields=["status"])

        return claim


class SupportMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportMessage
        fields = ("id", "name", "email", "message", "created_at", "processed")
        read_only_fields = ("created_at", "processed")


class UserStatusSerializer(serializers.ModelSerializer):
    user = UserListSerializer(read_only=True)

    class Meta:
        model = UserStatus
        fields = ("id", "user", "is_online", "is_blocked", "last_seen")
