from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    name = models.CharField(
       '公开名称', max_length=128, blank=True)
    site = models.CharField(
       '网站', max_length=50, blank=True)
    mod_date = models.DateTimeField('最后修改时间', auto_now=True)
    class Meta:
        verbose_name = '用户信息'
        verbose_name_plural = '用户信息'
    def __str__(self):
        return self.user.__str__()


class Setting(models.Model):
    '''常规设置'''
    name = models.CharField('键名', max_length=50, null=False, blank=False)
    slug = models.SlugField('别名', unique=True, blank=True)
    key = models.TextField('键值', null=True, blank=True)
    description = models.TextField('描述', null=True, blank=True)
    class Meta:
        verbose_name = '常规设置'
        verbose_name_plural = '常规设置'

    def __str__(self):
        return self.name

class MailSetting(models.Model):
    '''邮箱设置'''
    name = models.CharField('键名', max_length=50, null=False, blank=False)
    slug = models.SlugField('别名', unique=True, blank=True)
    key = models.TextField('键值', null=True, blank=True)
    description = models.TextField('描述', null=True, blank=True)
    class Meta:
        verbose_name = '邮箱设置'
        verbose_name_plural = '邮箱设置'

    def __str__(self):
        return self.name

class HomeSetting(models.Model):
    '''首页设置'''
    name = models.CharField('键名', max_length=50, null=False, blank=False)
    slug = models.SlugField('别名', unique=True, blank=True)
    key = models.TextField('键值', null=True, blank=True)
    description = models.TextField('描述', null=True, blank=True)
    class Meta:
        verbose_name = '首页设置'
        verbose_name_plural = '首页设置'

    def __str__(self):
        return self.name

class MenuSetting(models.Model):
    '''菜单设置'''
    name = models.CharField('键名', max_length=50, null=False, blank=False)
    slug = models.SlugField('别名', unique=True, blank=True)
    key = models.TextField('键值', null=True, blank=True)
    description = models.TextField('描述', null=True, blank=True)
    class Meta:
        verbose_name = '菜单设置'
        verbose_name_plural = '菜单设置'

    def __str__(self):
        return self.name