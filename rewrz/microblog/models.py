from django.db import models
# 导入 Django 内置用户模型
from django.contrib.auth.models import User

class Topic(models.Model):
    # 话题名称
    name = models.CharField('话题名称', max_length=50, null=False, blank=False)
    # 创建时间
    created_time = models.DateTimeField('发布时间', auto_now_add=True)
    # 最后修改时间
    modified_time = models.DateTimeField('修改时间', auto_now=True)

    class Meta:
        verbose_name = '话题'
        verbose_name_plural = '话题'

    def __str__(self):
        return self.name

class Tweet(models.Model):
    # 推文
    content = models.TextField('正文', max_length=500, null=True, blank=True)
    # 创建时间
    created_time = models.DateTimeField('发布时间', auto_now_add=True)
    # 最后修改时间
    modified_time = models.DateTimeField('修改时间', auto_now=True)
    # 微博作者，一对多
    author = models.ForeignKey(User, verbose_name='作者', default=User, on_delete=models.CASCADE)
    # 话题，多对多
    topic = models.ManyToManyField(Topic, verbose_name='话题', blank=True)

    class Meta:  # order by time
        verbose_name = '微博客'
        verbose_name_plural = '微博客'
        ordering = ['-created_time']