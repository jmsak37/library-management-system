from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Author, Book, Borrow

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

class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = "__all__"

class BookSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    author_id = serializers.PrimaryKeyRelatedField(
        source='author', queryset=Author.objects.all(), write_only=True, required=True
    )

    class Meta:
        model = Book
        fields = ("id", "title", "isbn", "author", "author_id", "publication_year", "copies_available")

class BorrowSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)
    book_id = serializers.PrimaryKeyRelatedField(
        source='book', queryset=Book.objects.all(), write_only=True
    )

    class Meta:
        model = Borrow
        fields = ("id", "user", "book", "book_id", "borrow_date", "return_date", "status")
        read_only_fields = ("user", "borrow_date", "return_date", "status")
