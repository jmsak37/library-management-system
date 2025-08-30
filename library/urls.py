from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    RegisterView,
    AuthorViewSet,
    BookViewSet,
    BorrowCreateView,
    ReturnView,
    MyBorrowsView,
    BorrowListAdminView,
    ReportLostView,
    ApproveFineView,
    ClaimListCreateView,
    ClaimActionView,
    ClaimsApproveFallbackView,
    ClaimDetailView,
    # new endpoints
    UsersListView,
    AdminCreateUserView,
    UserStatusView,
    SupportMessageCreateView,
)

router = DefaultRouter()
router.register(r'authors', AuthorViewSet, basename='author')
router.register(r'books', BookViewSet, basename='book')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('borrow/', BorrowCreateView.as_view(), name='borrow'),
    path('return/', ReturnView.as_view(), name='return'),
    path('report-lost/', ReportLostView.as_view(), name='report-lost'),
    path('approve-fine/', ApproveFineView.as_view(), name='approve-fine'),
    path('my-borrows/', MyBorrowsView.as_view(), name='my-borrows'),
    path('borrows/', BorrowListAdminView.as_view(), name='borrows-all'),

    # claims
    path('claims/', ClaimListCreateView.as_view(), name='claims-list-create'),
    path('claims/<int:pk>/', ClaimDetailView.as_view(), name='claim-detail'),
    path('claims/<int:pk>/<str:action>/', ClaimActionView.as_view(), name='claims-action'),
    path('claims/approve/', ClaimsApproveFallbackView.as_view(), name='claims_approve_fallback'),

    # admin/helper endpoints
    path('users/', UsersListView.as_view(), name='users-list'),
    path('users/create/', AdminCreateUserView.as_view(), name='users-create'),
    path('users/<int:pk>/status/', UserStatusView.as_view(), name='user-status'),

    # public support/chat
    path('support-messages/', SupportMessageCreateView.as_view(), name='support-messages'),
]
