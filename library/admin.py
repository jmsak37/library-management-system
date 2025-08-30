from django.contrib import admin
from .models import Author, Book, Borrow, UserStatus, SupportMessage, Claim

admin.site.register(Author)
admin.site.register(Book)
admin.site.register(Borrow)
admin.site.register(Claim)
admin.site.register(UserStatus)
admin.site.register(SupportMessage)
