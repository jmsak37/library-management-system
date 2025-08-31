from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth import get_user_model

from rest_framework import generics, viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes

from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from .permissions import IsAdminOrReadOnly
from .models import Author, Book, Borrow, Claim, UserStatus, SupportMessage
from .serializers import (
    UserRegisterSerializer,
    UserListSerializer,
    AuthorSerializer,
    BookSerializer,
    BorrowSerializer,
    ClaimSerializer,
    SupportMessageSerializer,
    UserStatusSerializer,
)

User = get_user_model()


# Registration
class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]


class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all().order_by('name')
    serializer_class = AuthorSerializer
    permission_classes = [IsAdminOrReadOnly]


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.select_related('author').all().order_by('title')
    serializer_class = BookSerializer
    permission_classes = [IsAdminOrReadOnly]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['publication_year', 'copies_available', 'author']
    search_fields = ['title', 'isbn', 'author__name']
    ordering_fields = ['title', 'publication_year', 'copies_available']

    def get_queryset(self):
        qs = super().get_queryset()
        available = self.request.query_params.get("available")
        if available and available.lower() in ("1", "true", "yes"):
            qs = qs.filter(copies_available__gt=0)

        title = self.request.query_params.get("title")
        isbn = self.request.query_params.get("isbn")
        if title:
            qs = qs.filter(title__icontains=title)
        if isbn:
            qs = qs.filter(isbn__icontains=isbn)
        return qs


class BorrowCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data or {}
        book_id = data.get("book_id")
        if not book_id:
            return Response({"detail": "book_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        book = get_object_or_404(Book, pk=book_id)

        # Determine target user: admin can specify username or user_id
        target_user = request.user
        if request.user.is_staff:
            username = data.get("username")
            user_id = data.get("user_id")
            if username:
                try:
                    target_user = User.objects.get(username=username)
                except User.DoesNotExist:
                    return Response({"detail": f"username '{username}' not found"}, status=status.HTTP_400_BAD_REQUEST)
            elif user_id:
                try:
                    target_user = User.objects.get(pk=user_id)
                except User.DoesNotExist:
                    return Response({"detail": f"user_id '{user_id}' not found"}, status=status.HTTP_400_BAD_REQUEST)

        active = Borrow.objects.filter(user=target_user, book=book).exclude(status__iexact="returned").exists()
        if active:
            return Response({"detail": "User already has an active borrow for this book"}, status=status.HTTP_400_BAD_REQUEST)

        if book.copies_available <= 0:
            return Response({"detail": "No copies available"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if target_user is blocked
        try:
            status_obj = getattr(target_user, "status", None)
            if status_obj and status_obj.is_blocked and not request.user.is_staff:
                return Response({"detail": "User is blocked"}, status=status.HTTP_403_FORBIDDEN)
        except Exception:
            pass

        # decrement copy and create borrow
        book.copies_available -= 1
        book.save()
        borrow = Borrow.objects.create(user=target_user, book=book, status="borrowed")
        serializer = BorrowSerializer(borrow, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ReturnView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        borrow_id = request.data.get("borrow_id")
        if not borrow_id:
            return Response({"detail": "borrow_id required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            borrow = Borrow.objects.select_for_update().get(pk=borrow_id)
        except Borrow.DoesNotExist:
            return Response({"detail": "Borrow not found"}, status=status.HTTP_404_NOT_FOUND)

        if borrow.user != request.user and not request.user.is_staff:
            return Response({"detail": "Not allowed to return this borrow"}, status=status.HTTP_403_FORBIDDEN)

        if str(getattr(borrow, "status", "")).lower() != Borrow.STATUS_BORROWED:
            return Response({"detail": "Borrow is already returned or not in 'borrowed' state"}, status=status.HTTP_400_BAD_REQUEST)

        existing_return = Borrow.objects.filter(
            user=borrow.user,
            book=borrow.book,
            status__iexact="returned"
        ).exclude(pk=borrow.pk).first()

        if existing_return:
            existing_return.delete()

        borrow.status = Borrow.STATUS_RETURNED
        borrow.return_date = timezone.now()

        try:
            borrow.save()
        except IntegrityError as e:
            return Response({"detail": "Database integrity error while returning borrow", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        book = borrow.book
        book.copies_available = (book.copies_available or 0) + 1
        book.save()

        serializer = BorrowSerializer(borrow, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ReportLostView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        borrow_id = request.data.get("borrow_id")
        if not borrow_id:
            return Response({"detail": "borrow_id required"}, status=status.HTTP_400_BAD_REQUEST)

        borrow = get_object_or_404(Borrow, pk=borrow_id)

        if borrow.user != request.user and not request.user.is_staff:
            return Response({"detail": "Not allowed to report this borrow"}, status=status.HTTP_403_FORBIDDEN)

        if str(borrow.status).lower() == Borrow.STATUS_LOST:
            return Response({"detail": "Borrow already marked lost"}, status=status.HTTP_400_BAD_REQUEST)

        # set lost, set fine_due based on book.lost_fine if available
        borrow.status = Borrow.STATUS_LOST
        borrow.fine_due = borrow.book.lost_fine or borrow.fine_due
        borrow.fine_paid = False
        borrow.save()

        serializer = BorrowSerializer(borrow, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ApproveFineView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @transaction.atomic
    def post(self, request):
        borrow_id = request.data.get("borrow_id")
        if not borrow_id:
            return Response({"detail": "borrow_id required"}, status=status.HTTP_400_BAD_REQUEST)

        borrow = get_object_or_404(Borrow, pk=borrow_id)

        # mark fine paid
        borrow.fine_paid = True
        borrow.save()

        # If borrow was lost, attempt to mark returned and increment copies
        if borrow.status == Borrow.STATUS_LOST:
            try:
                # try to mark this borrow returned; handle unique_together collisions
                borrow.status = Borrow.STATUS_RETURNED
                borrow.return_date = timezone.now()
                borrow.save()
            except IntegrityError:
                existing = Borrow.objects.filter(user=borrow.user, book=borrow.book, status=Borrow.STATUS_RETURNED).first()
                if existing:
                    existing.return_date = timezone.now()
                    existing.save()
                    # remove the lost record (we consider it merged)
                    borrow.delete()
                    borrow = existing
                else:
                    raise

            # increment book copies
            book = borrow.book
            book.copies_available = (book.copies_available or 0) + 1
            book.save()

        serializer = BorrowSerializer(borrow, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class MyBorrowsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BorrowSerializer

    def get_queryset(self):
        return Borrow.objects.filter(user=self.request.user).select_related('book', 'book__author').order_by('-borrow_date')


class BorrowListAdminView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = BorrowSerializer
    queryset = Borrow.objects.select_related('book', 'user', 'book__author').all().order_by('-borrow_date')


# Claims endpoints
class ClaimListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # admin: list all, user: list own
        if request.user.is_staff:
            qs = Claim.objects.select_related('borrow', 'user').all().order_by('-created_at')
        else:
            qs = Claim.objects.filter(user=request.user).select_related('borrow').order_by('-created_at')
        serializer = ClaimSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        borrow_id = request.data.get("borrow_id")
        claim_type = request.data.get("type")
        offered_amount = request.data.get("offered_amount", None)
        message = request.data.get("message", "")

        if not borrow_id or not claim_type:
            return Response({"detail": "borrow_id and type are required"}, status=status.HTTP_400_BAD_REQUEST)

        borrow = get_object_or_404(Borrow, pk=borrow_id)

        # only borrower (or admin on behalf) may create claims
        if request.user != borrow.user and not request.user.is_staff:
            return Response({"detail": "Not allowed to create claim for this borrow"}, status=status.HTTP_403_FORBIDDEN)

        # If fine already paid, disallow 'saw' claims
        if claim_type == Claim.TYPE_SAW and borrow.fine_paid:
            return Response({"detail": "Cannot claim 'saw' when fine already paid"}, status=status.HTTP_400_BAD_REQUEST)

        # If claim_type == saw and borrow.status == lost and offered_amount not provided,
        # default offered_amount to 1/4 of book.lost_fine — BUT if lost_fine is 0, do not compute (leave None)
        offered_dec = None
        if offered_amount not in (None, ''):
            try:
                offered_dec = Decimal(offered_amount)
            except Exception:
                return Response({"detail": "Invalid offered_amount"}, status=status.HTTP_400_BAD_REQUEST)

            if offered_dec < 0:
                return Response({"detail": "offered_amount must be >= 0"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if claim_type == Claim.TYPE_SAW and borrow.status == Borrow.STATUS_LOST:
                # compute 1/4 of book lost fine only if lost_fine > 0
                try:
                    base_fine = borrow.book.lost_fine or Decimal("0.00")
                except Exception:
                    base_fine = Decimal("0.00")
                if base_fine == Decimal("0.00"):
                    offered_dec = None
                else:
                    offered_dec = (base_fine * Decimal("0.25"))
                    # keep full precision; backend can round/store as needed

        # Create claim
        claim = Claim.objects.create(
            borrow=borrow,
            user=request.user,
            type=claim_type,
            message=message or "",
            offered_amount=offered_dec
        )
        serializer = ClaimSerializer(claim, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ClaimDetailView(APIView):
    """
    GET a single claim or DELETE it (admin-only deletion).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        claim = get_object_or_404(Claim, pk=pk)
        # owner or admin can fetch
        if claim.user != request.user and not request.user.is_staff:
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ClaimSerializer(claim, context={'request': request})
        return Response(serializer.data)

    def delete(self, request, pk):
        # only admin may delete claims (per your requirement)
        if not request.user.is_staff:
            return Response({"detail": "Admin required to delete claims"}, status=status.HTTP_403_FORBIDDEN)
        claim = get_object_or_404(Claim, pk=pk)
        claim.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClaimActionView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @transaction.atomic
    def post(self, request, pk, action):
        claim = get_object_or_404(Claim, pk=pk)
        if action not in ('approve', 'decline'):
            return Response({"detail": "invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        claim.reviewed_by = request.user
        claim.reviewed_at = timezone.now()

        if action == 'approve':
            claim.status = Claim.STATUS_APPROVED
            claim.save()

            borrow = claim.borrow

            # APPROVE SAW: set fine_due to offered_amount (if present), mark fine_paid True,
            # mark borrow returned and increment book copies.
            if claim.type == Claim.TYPE_SAW:
                # offered_amount may be None; in that case, fall back to existing fine_due
                if claim.offered_amount is not None:
                    borrow.fine_due = claim.offered_amount
                # mark paid
                borrow.fine_paid = True

                # Mark as returned and increment copies (handle unique_together collisions)
                try:
                    borrow.status = Borrow.STATUS_RETURNED
                    borrow.return_date = timezone.now()
                    borrow.save()
                except IntegrityError:
                    existing = Borrow.objects.filter(user=borrow.user, book=borrow.book, status=Borrow.STATUS_RETURNED).first()
                    if existing:
                        existing.return_date = timezone.now()
                        existing.save()
                        borrow.delete()
                        borrow = existing
                    else:
                        raise

                book = borrow.book
                book.copies_available = (book.copies_available or 0) + 1
                book.save()

                borrow.save()
                return Response({"detail": "saw-claim approved: fine marked paid and borrow returned"}, status=status.HTTP_200_OK)

            # APPROVE RETURNED: mark borrow returned and increment copies
            if claim.type == Claim.TYPE_RETURNED:
                borrow = claim.borrow
                if borrow.status != Borrow.STATUS_RETURNED:
                    try:
                        borrow.status = Borrow.STATUS_RETURNED
                        borrow.return_date = timezone.now()
                        borrow.save()
                    except IntegrityError:
                        existing = Borrow.objects.filter(user=borrow.user, book=borrow.book, status=Borrow.STATUS_RETURNED).first()
                        if existing:
                            existing.return_date = timezone.now()
                            existing.save()
                            borrow.delete()
                            borrow = existing
                        else:
                            raise
                    book = borrow.book
                    book.copies_available = (book.copies_available or 0) + 1
                    book.save()

                return Response({"detail": "returned-claim approved: borrow marked returned"}, status=status.HTTP_200_OK)

            # fallback
            return Response({"detail": "claim approved"}, status=status.HTTP_200_OK)

        else:
            claim.status = Claim.STATUS_DECLINED
            claim.save()
            return Response({"detail": "claim declined"}, status=status.HTTP_200_OK)


class ClaimsApproveFallbackView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @transaction.atomic
    def post(self, request):
        claim_id = request.data.get('claim_id')
        approve = request.data.get('approve', True)

        if claim_id is None:
            return Response({'detail': 'claim_id required'}, status=status.HTTP_400_BAD_REQUEST)

        claim = get_object_or_404(Claim, pk=claim_id)

        # record review metadata
        claim.reviewed_by = request.user
        claim.reviewed_at = timezone.now()

        if not approve:
            claim.status = Claim.STATUS_DECLINED
            claim.save()
            return Response({'detail': 'claim declined'}, status=status.HTTP_200_OK)

        # Approve flow (reuse same logic as ClaimActionView.approve)
        borrow = claim.borrow

        if claim.type == Claim.TYPE_SAW:
            # if offered_amount present, apply it; otherwise if book.lost_fine > 0
            # and offered_amount omitted we set offered to 1/4 (but if lost_fine is 0, treat as zero)
            if claim.offered_amount is None:
                book_fine = borrow.book.lost_fine if getattr(borrow.book, "lost_fine", None) is not None else Decimal("0.00")
                if book_fine != Decimal("0.00"):
                    claim.offered_amount = (book_fine * Decimal("0.25")).quantize(Decimal("0.01"))
                else:
                    claim.offered_amount = Decimal("0.00")

            # apply offered amount to fine_due
            if claim.offered_amount is not None:
                remaining = (borrow.fine_due or Decimal("0.00")) - claim.offered_amount
                if remaining <= Decimal("0.00"):
                    # fully covered -> clear fine, mark paid and if lost, mark returned & restore copy
                    borrow.fine_due = Decimal("0.00")
                    borrow.fine_paid = True
                    if borrow.status == Borrow.STATUS_LOST:
                        borrow.status = Borrow.STATUS_RETURNED
                        borrow.return_date = timezone.now()
                        # handle unique_together collisions: try save, otherwise merge with existing returned record
                        try:
                            borrow.save()
                        except IntegrityError:
                            existing = Borrow.objects.filter(user=borrow.user, book=borrow.book, status=Borrow.STATUS_RETURNED).first()
                            if existing:
                                existing.return_date = timezone.now()
                                existing.save()
                                # delete the lost record and use existing
                                borrow.delete()
                                borrow = existing
                            else:
                                raise
                        # increment book copies
                        book = borrow.book
                        book.copies_available = (book.copies_available or 0) + 1
                        book.save()
                else:
                    borrow.fine_due = remaining
                    # do not mark as paid if remaining > 0
                borrow.save()
            claim.status = Claim.STATUS_APPROVED
            claim.save()
            return Response({'detail': 'claim approved and fine updated/borrow possibly returned'}, status=status.HTTP_200_OK)

        elif claim.type == Claim.TYPE_RETURNED:
            # approve returned claim: clear fine, mark paid, set borrow returned and increment copies
            borrow.fine_due = Decimal('0.00')
            borrow.fine_paid = True
            if borrow.status != Borrow.STATUS_RETURNED:
                try:
                    borrow.status = Borrow.STATUS_RETURNED
                    borrow.return_date = timezone.now()
                    borrow.save()
                except IntegrityError:
                    existing = Borrow.objects.filter(user=borrow.user, book=borrow.book, status=Borrow.STATUS_RETURNED).first()
                    if existing:
                        existing.return_date = timezone.now()
                        existing.save()
                        borrow.delete()
                        borrow = existing
                    else:
                        raise
                book = borrow.book
                book.copies_available = (book.copies_available or 0) + 1
                book.save()
            claim.status = Claim.STATUS_APPROVED
            claim.save()
            return Response({'detail': 'returned claim approved; borrow marked returned'}, status=status.HTTP_200_OK)

        else:
            return Response({'detail': 'unknown claim type'}, status=status.HTTP_400_BAD_REQUEST)


# --- New admin & utility endpoints ---


class UsersListView(APIView):
    """
    Return a list of non-staff users for admin UIs to let admin pick username (registration number).
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        qs = User.objects.filter(is_staff=False).order_by('username')
        serializer = UserListSerializer(qs, many=True)
        return Response(serializer.data)


class AdminCreateUserView(APIView):
    """
    Admin-only endpoint for creating a new user (with optional is_staff flag).
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email', '')
        password = request.data.get('password', 'welcome')
        is_staff = bool(request.data.get('is_staff', False))

        if not username:
            return Response({"detail": "username required"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"detail": "username already exists"}, status=status.HTTP_400_BAD_REQUEST)

        user = User(username=username, email=email, is_staff=is_staff)
        user.set_password(password)
        user.save()
        # ensure a UserStatus exists
        UserStatus.objects.get_or_create(user=user)
        return Response({"id": user.id, "username": user.username, "email": user.email, "is_staff": user.is_staff}, status=status.HTTP_201_CREATED)


class UserStatusView(APIView):
    """
    Admin can update a user's status (is_online, is_blocked) and reset password to 'welcome'.
    """
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        is_online = request.data.get('is_online', None)
        is_blocked = request.data.get('is_blocked', None)
        reset_password = bool(request.data.get('reset_password', False))

        status_obj, _ = UserStatus.objects.get_or_create(user=user)
        changed = False

        if is_online is not None:
            status_obj.is_online = bool(is_online)
            status_obj.last_seen = timezone.now()
            changed = True

        if is_blocked is not None:
            status_obj.is_blocked = bool(is_blocked)
            changed = True

        if changed:
            status_obj.save()

        if reset_password:
            user.set_password("welcome")
            user.save()
            # optionally mark status (admin could log user out in token store if implemented)
        return Response({"detail": "status updated", "is_online": status_obj.is_online, "is_blocked": status_obj.is_blocked})


class SupportMessageCreateView(APIView):
    """
    Allow any visitor (authenticated or not) to create a support message/to-admin message.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SupportMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
