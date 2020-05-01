# 该文件是用来更换 Jinja2 引擎所用
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse
from blog.templatetags.blog_tags import get_categories,get_recent_posts,get_tags,archives
from mptt.templatetags import mptt_tags

from jinja2 import Environment


def environment(**options):
    env = Environment(**options)
    env.globals.update({
        'static': staticfiles_storage.url,
        'url': reverse,
        'get_categories': get_categories,
        'get_tags': get_tags,
        'get_recent_posts': get_recent_posts,
        'archives': archives,
        'mptt_tags': mptt_tags,
        'mptt_recursetree': mptt_tags.recursetree,
    })
    return env