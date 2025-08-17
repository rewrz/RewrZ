from django.contrib import admin
from .models import Setting, MailSetting, HomeSetting, MenuSetting, UserProfile
# Register your models here.

class SettingAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'description']

class MailSettingAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'description']

class HomeSettingAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'description']

admin.site.register(Setting, SettingAdmin)
admin.site.register(MailSetting, MailSettingAdmin)
admin.site.register(HomeSetting, HomeSettingAdmin)
admin.site.register(MenuSetting)
admin.site.register(UserProfile)