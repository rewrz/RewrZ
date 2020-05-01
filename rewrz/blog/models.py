from django.db import models
# 导入 Django 内置用户模型
from django.contrib.auth.models import User
from django.urls import reverse
import datetime,time
from django.utils.html import strip_tags
from ckeditor_uploader.fields import RichTextUploadingField
from pyquery import PyQuery as pq
from django.conf import settings
# Create your models here.

class Category(models.Model):
    """
    分类(name 名称, slug 别名，img 图片，description 描述)
    """
    name = models.CharField('分类名', max_length=100)
    slug = models.SlugField('别名', unique=True)
    img = models.CharField('图片', max_length=200, null=True, blank=True)
    description = models.CharField('描述', max_length=110, null=True, blank=True)

    class Meta:
        verbose_name = '分类'
        verbose_name_plural = '分类'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        if settings.POST_FIXED_LINK is True:
            return reverse('blog:category_slug', kwargs={'slug': self.slug})
        else:
            return reverse('blog:category', kwargs={'pk': self.pk})

class Tag(models.Model):
    """
    标签(name 名称，slug 别名，description 描述)
    """
    name = models.CharField('标签名', max_length=100)
    slug = models.SlugField('别名', unique=True)

    class Meta:
        verbose_name = '标签'
        verbose_name_plural = '标签'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        if settings.POST_FIXED_LINK is True:
            return reverse('blog:tag_slug', kwargs={'slug': self.slug})
        else:
            return reverse('blog:tag', kwargs={'pk': self.pk})

class Post(models.Model):
    """
    文章
    """
    # 文章标题
    title = models.CharField('文章标题', max_length=100)
    # 封面图片
    coverimg = models.CharField('封面图片', max_length=2000, null=True, blank=True, default=None)
    # 别名
    slug = models.SlugField('别名', unique=True, blank=True)
    # 文章正文
    body = RichTextUploadingField('正文', null=True, blank=True)
    # 创建时间
    created_time = models.DateTimeField('发布时间', auto_now_add = True)
    # 最后修改时间
    modified_time = models.DateTimeField('修改时间',auto_now= True)
    # 文章摘要，声明可以为空
    excerpt = models.CharField('摘要', max_length=300, blank=True)
    # 阅读次数
    views = models.PositiveIntegerField('阅读次数', default=0)
    # 分类，一对多
    # 在django2.0后，定义外键和一对一关系的时候需要加on_delete选项，此参数为了避免两个表里的数据不一致问题，不然会报错，一般情况下使用CASCADE
    category = models.ForeignKey(Category, verbose_name='分类', null=True, blank=True, on_delete=models.CASCADE)
    # 标签，多对多
    tags = models.ManyToManyField(Tag, verbose_name='标签', blank=True)
    # 文章作者，一对多
    author = models.ForeignKey(User, verbose_name='作者', null=False, blank=False, default=User, on_delete=models.CASCADE)

    class Meta:  # order by time
        verbose_name = '文章'
        verbose_name_plural = '文章'
        ordering = ['-created_time']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        if settings.POST_FIXED_LINK is True:
            return reverse('blog:detail_slug', kwargs={'slug': self.slug})
        else:
            return reverse('blog:detail', kwargs={'pk': self.pk})

    def increase_views(self):
        self.views += 1
        self.save(update_fields=['views'])

    def save(self, *args, **kwargs):
        # 如果没有填写摘要
        if not self.excerpt:
            # strip_tags 去掉 HTML 文本的全部 HTML 标签
            # 从文本摘取前 200 个字符赋给 excerpt
            self.excerpt = strip_tags(self.body)[:300]
        # 如果没有填写别名
        if not self.slug:
            # 取当前时间值为slug
            self.slug = int(round(time.time()*10))
        # 如果没有填写封面
        if not self.coverimg:
            # 抓取文章第一张图片
            try:
                self.coverimg = pq(pq(Post.objects.filter(pk=str(self.id)).values('body')[0]['body']))('img').attr('src')
            except:
                pass

        # 调用父类的 save 方法将数据保存到数据库中
        super(Post, self).save(*args, **kwargs)

    # 获取后台文本编辑器图文内容中图片url地址
    def get_postimg_url(self):
        html = pq(Post.objects.filter(pk=str(self.id)).values('body')[0]['body'])  # 获取body字段内容（HTML）
        img_url = pq(html)('img').attr('src')  # 截取html内容中的图片路径
        return img_url  # 返回图片路径


