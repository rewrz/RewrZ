from django.contrib import admin
from .models import Comment,MicroComment
# Register your models here.

class CommentAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'url', 'text', 'created_time']

class MicroCommentAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'url', 'text', 'created_time']

admin.site.register(Comment, CommentAdmin)
admin.site.register(MicroComment, MicroCommentAdmin)