from django.contrib.syndication.views import Feed

from .models import Post
from django.conf import settings


class AllPostsRssFeed(Feed):
    # 显示在聚合阅读器上的标题
    title = settings.SITE_TITLE + ' - ' + settings.SITE_SUBTITLE

    # 通过聚合阅读器跳转到网站的地址
    link = "/"

    # 显示在聚合阅读器上的描述信息
    description = settings.SITE_TITLE + settings.SITE_DESCRIPTION

    # 需要显示的内容条目
    def items(self):
        return Post.objects.all()

    # 聚合器中显示的内容条目的标题
    def item_title(self, item):
        return '[%s] %s' % (item.category, item.title)

    # 聚合器中显示的内容条目的描述
    def item_description(self, item):
        return item.body