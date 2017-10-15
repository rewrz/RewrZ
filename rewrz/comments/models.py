from django.db import models
from hashlib import md5
# Create your models here.

class Comment(models.Model):
    name = models.CharField('评论人', max_length=100)
    email = models.EmailField('邮件', max_length=255)
    url = models.URLField('网址', null=True, blank=True)
    text = models.TextField('评论内容')
    created_time = models.DateTimeField('评论时间', auto_now_add=True)

    post = models.ForeignKey('blog.Post')
    parent = models.ForeignKey('Comment', null=True, blank=True, default=None)

    class Meta:  # order by time
        verbose_name = '评论'
        verbose_name_plural = '评论'
        ordering = ['-created_time']

    def __str__(self):
        return self.text[:20]

    # 返回Gravatar头像
    def avatar(self, size=64):
        return 'https://www.gravatar.com/avatar/' + md5(
            self.email.encode('utf8')).hexdigest() + '?d=mm&s=' + str(
            size)