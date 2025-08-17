from django.contrib import admin
from .models import Tweet, Topic
# Register your models here.

class TweetAdmin(admin.ModelAdmin):
    list_display = ['author', 'content', 'created_time', 'modified_time']

admin.site.register(Tweet, TweetAdmin)
admin.site.register(Topic)