from django.db import models
from hashlib import md5
# django-mptt
from mptt.models import MPTTModel, TreeForeignKey
# Create your models here.

class Comment(MPTTModel):
    name = models.CharField('评论人', max_length=100)
    email = models.EmailField('邮件', max_length=255)
    url = models.URLField('网址', null=True, blank=True)
    text = models.TextField('评论内容')
    created_time = models.DateTimeField('评论时间', auto_now_add=True)

    post = models.ForeignKey('blog.Post', on_delete=models.CASCADE)
    # mptt树形结构
    parent = TreeForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    # 记录二级评论回复对象
    reply_to = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replyers'
    )

    # 替换 Meta 为 MPTTMeta
    class MPTTMeta:  # order by time
        verbose_name = '评论'
        verbose_name_plural = '评论'
        order_insertion_by = ['created_time']

    def __str__(self):
        return self.text[:20]

    # 返回Gravatar头像
    def avatar(self, size=64):
        return 'https://www.gravatar.com/avatar/' + md5(
            self.email.encode('utf8')).hexdigest() + '?d=mm&s=' + str(
            size)


class MicroComment(MPTTModel):
    name = models.CharField('评论人', max_length=100)
    email = models.EmailField('邮件', max_length=255)
    url = models.URLField('网址', null=True, blank=True)
    text = models.TextField('评论内容')
    created_time = models.DateTimeField('评论时间', auto_now_add=True)

    post = models.ForeignKey('microblog.Tweet', on_delete=models.CASCADE)
    # mptt树形结构
    parent = TreeForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    # 记录二级评论回复对象
    reply_to = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replyers'
    )

    class MPTTMeta:  # order by time
        verbose_name = '微博客评论'
        verbose_name_plural = '微博客评论'
        order_insertion_by = ['-created_time']

    def __str__(self):
        return self.text[:20]

    # 返回Gravatar头像
    def avatar(self, size=64):
        return 'https://www.gravatar.com/avatar/' + md5(
            self.email.encode('utf8')).hexdigest() + '?d=mm&s=' + str(
            size)