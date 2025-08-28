from django.shortcuts import render

# Create your views here.
from rest_framework import permissions
from .permissions import IsAdminOrReadOnly


from rest_framework import filters

from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from .models import Author, Book, Borrow
from .serializers import (UserRegisterSerializer, AuthorSerializer, BookSerializer, BorrowSerializer)

# Registration
class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]

# Authors and Books as viewsets
class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.select_related('author').all()
    serializer_class = BookSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        # simple filter: ?available=true
        available = self.request.query_params.get("available")
        if available and available.lower() in ("1", "true", "yes"):
            qs = qs.filter(copies_available__gt=0)
        # title, isbn simple filters
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
        user = request.user
        book_id = request.data.get("book_id")
        if not book_id:
            return Response({"detail": "book_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        book = get_object_or_404(Book, pk=book_id)

        # business rules:
        if book.copies_available <= 0:
            return Response({"detail": "No copies available"}, status=status.HTTP_400_BAD_REQUEST)

        # check if user already has an active borrow for this book
        active = Borrow.objects.filter(user=user, book=book, status="BORROWED").exists()
        if active:
            return Response({"detail": "You already borrowed this book"}, status=status.HTTP_400_BAD_REQUEST)

        # decrement copy and create borrow
        book.copies_available -= 1
        book.save()
        borrow = Borrow.objects.create(user=user, book=book, status="BORROWED")
        serializer = BorrowSerializer(borrow)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class ReturnView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        borrow_id = request.data.get("borrow_id")
        if not borrow_id:
            return Response({"detail": "borrow_id required"}, status=status.HTTP_400_BAD_REQUEST)
        borrow = get_object_or_404(Borrow, pk=borrow_id, user=request.user)

        if borrow.status != "BORROWED":
            return Response({"detail": "Borrow is already returned"}, status=status.HTTP_400_BAD_REQUEST)

        borrow.status = "RETURNED"
        from django.utils import timezone
        borrow.return_date = timezone.now()
        borrow.save()

        book = borrow.book
        book.copies_available += 1
        book.save()

        serializer = BorrowSerializer(borrow)
        return Response(serializer.data)

class MyBorrowsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BorrowSerializer

    def get_queryset(self):
        return Borrow.objects.filter(user=self.request.user).select_related('book', 'book__author')

# AuthorViewSet & BookViewSet: use IsAdminOrReadOnly
class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    permission_classes = [IsAdminOrReadOnly]

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.select_related('author').all()
    serializer_class = BookSerializer
    permission_classes = [IsAdminOrReadOnly]
    # get_queryset already uses query params for filtering

# Borrow views
class BorrowListAdminView(generics.ListAPIView):
    # Admin-only list of all borrows
    permission_classes = [permissions.IsAdminUser]
    serializer_class = BorrowSerializer
    queryset = Borrow.objects.select_related('book', 'user', 'book__author').all()

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.select_related('author').all()
    serializer_class = BookSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'isbn', 'author__name']
    filterset_fields = ['copies_available']  # you can filter copies_available__gt=0 client-side

    def get_queryset(self):
        qs = super().get_queryset()
        available = self.request.query_params.get("available")
        if available and available.lower() in ("1", "true", "yes"):
            qs = qs.filter(copies_available__gt=0)
        return qs