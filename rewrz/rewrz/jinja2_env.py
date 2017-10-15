# 该文件是用来更换 Jinja2 引擎所用
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.urlresolvers import reverse

from jinja2 import Environment


def environment(**options):
    env = Environment(**options)
    env.globals.update({
        'static': staticfiles_storage.url,
        'url': reverse,
    })
    return env