from django.urls import path, include
from rest_framework.routers import DefaultRouter

# library/urls.py (router already present)
from .views import BorrowListAdminView

from .views import RegisterView, AuthorViewSet, BookViewSet, BorrowCreateView, ReturnView, MyBorrowsView

router = DefaultRouter()
router.register(r'authors', AuthorViewSet, basename='author')
router.register(r'books', BookViewSet, basename='book')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('borrow/', BorrowCreateView.as_view(), name='borrow'),
    path('return/', ReturnView.as_view(), name='return'),
    path('my-borrows/', MyBorrowsView.as_view(), name='my-borrows'),
    path("borrows/", BorrowListAdminView.as_view(), name="borrows-all"),
]
