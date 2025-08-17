from django.conf.urls import url, re_path

from . import views

app_name = 'portal'

urlpatterns = [
    #url(r'^$', views.index, name='index'),
    url(r'^$', views.IndexView.as_view(), name='index'),
    url(r'^adminz/', views.RzAdmin, name='rz-admin'),
    re_path(r'^registerz/$', views.register, name='register'),
    re_path(r'^loginz/$', views.login, name='login'),
    #re_path(r'^user/(?P<pk>\d+)/profile/$', views.profile, name='profile'),
    #re_path(r'^user/(?P<pk>\d+)/profile/update/$', views.profile_update, name='profile_update'),
    #re_path(r'^user/(?P<pk>\d+)/pwdchange/$', views.pwd_change, name='pwd_change'),
    #re_path(r'^logout/$', views.logout, name='logout'),
]