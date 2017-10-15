from ..models import Post, Category, Tag
from django.db.models.aggregates import Count
from django import template


register = template.Library()

# 最近文章
@register.simple_tag
def get_recent_posts(num=9):
    return Post.objects.all().order_by('-modified_time')[:num]

# 按月归档
@register.simple_tag
def archives():
    return Post.objects.dates('created_time', 'month', order='DESC')

# 分类归档
@register.simple_tag
def get_categories():
    return Category.objects.annotate(num_posts=Count('post')).filter(num_posts__gt=0)

# 标签云
@register.simple_tag
def get_tags():
    return Tag.objects.annotate(num_posts=Count('post')).filter(num_posts__gt=0)