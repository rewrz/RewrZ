"""rewrz URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.contrib import admin
from django.views.static import serve
from django.conf import settings
from portal.views import MySeachView, permission_denied, page_not_found, page_error
from comments.views import refresh_captcha, check_captcha
from blog.feeds import AllPostsRssFeed
from django_otp.admin import OTPAdminSite

if settings.OTP_ENABLE:
    admin.site.__class__ = OTPAdminSite

admin.site.site_header = settings.ADMIN_SITE_HEADER
admin.site.index_title = settings.ADMIN_INDEX_TITLE
admin.site.site_title = settings.ADMIN_SITE_TITLE

# 定义错误跳转页面
handler403 = permission_denied
handler404 = page_not_found
handler500 = page_error

urlpatterns = [
    url(r'^jet/', include('jet.urls', 'jet')),  # Django JET URLS
    url(r'^jet/dashboard/', include('jet.dashboard.urls', 'jet-dashboard')),  # Django JET dashboard URLS
    url(r'^wp-admin/', admin.site.urls), # 注册后台管理地址
    # url(r'auth/', include('portal.urls')),
    url(r'', include('portal.urls')),
    url(r'', include('blog.urls')),
    url(r'', include('comments.urls')),
    # url(r'^search/', include('haystack.urls')), # 全文搜索
    url(r'^search/', MySeachView(), name='haystack_search'),  # 自定义高亮搜索视图
    url(r'^ckeditor/', include('ckeditor_uploader.urls')),# ckeditor富文本编辑器
    url(r'^media/(?P<path>.*)/$', serve, {"document_root": settings.MEDIA_ROOT}), # media上传文件urls
    url(r'^all/rss/$', AllPostsRssFeed(), name='rss'), # RSS订阅
    url('captcha/', include('captcha.urls')),# 图片验证码
    url('refresh_captcha/', refresh_captcha, name='refresh_captcha'),# 刷新验证码，ajax
    url('check_captcha/', check_captcha, name='check_captcha'),# 验证验证码，ajax
]
