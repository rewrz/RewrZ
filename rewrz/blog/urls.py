from django.conf.urls import url, include
from . import views

app_name = 'blog'
urlpatterns = [
    url(r'^blog/$', views.BlogView.as_view(), name='index'),
    # url(r'^post/(?P<pk>[0-9]+)/$', views.detail, name='detail'),
    url(r'^p/(?P<pk>[0-9]+)/$', views.PostDetailView.as_view(), name='detail'),
    url(r'^archive/(?P<slug>.+)/$', views.PostDetailViewSlug.as_view(), name='detail_slug'),
    url(r'^archives/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})/$', views.archives, name='archives'),
    url(r'^cat/(?P<pk>[0-9]+)/$', views.category, name='category'),
    # url(r'^category/(?P<pk>[0-9]+)/$', views.CategoryView.as_view(), name='category'),
    url(r'^category/(?P<slug>.+)/$', views.category_slug, name='category_slug'),
    # url(r'^tag/(?P<pk>[0-9]+)/$', views.TagView.as_view(), name='tag'),
    url(r'^tag/(?P<pk>[0-9]+)/$', views.tag, name='tag'),
    url(r'^label/(?P<slug>.+)/$', views.tag_slug, name='tag_slug'),
]