from akismet import Akismet
from django.conf import settings
from datetime import datetime
# 修改自 https://github.com/mixkorshun/django-antispam
# 原 MIT License

def get_connection(key=None, blog_url=None):
    """
    Get Akismet client object.
    If no connection params provided, use params from django project settings.
    :param api_key: Akismet API key
    :param blog: blog base url
    :param is_test: test mode
    :rtype: akismet.Akismet
    :return: akismet client
    """
    ak = Akismet(
        key = key or getattr(settings, 'AKISMET_API_KEY'),
        blog_url = blog_url or getattr(settings, 'AKISMET_SITE_URL', None),
    )
    return ak


def check(request, comment):
    """
    Checks given comment to spam by Akismet.
    :type request: antispam.akismet.Request
    :type comment: antispam.akismet.Comment
    :return: True if comment is spam, otherwise False
    """
    params = {}
    params.update(request.as_params())
    params.update(comment.as_params())
    params.update({
            'is_test': getattr(settings, 'AKISMET_TEST_MODE', False),
    })
    client = get_connection()
    check_result = client.comment_check(**params)
    return check_result


def submit(request, comment, is_spam):
    """
    Submit given comment to Akismet.
    Information about the comment status must be provided (spam/not spam).
    :type request: antispam.akismet.Request
    :type comment: antispam.akismet.Comment
    :type is_spam: bool
    """
    params = {}
    params.update(request.as_params())
    params.update(comment.as_params())

    connection = get_connection()
    connection.submit_spam(**params)

def get_client_ip(request):
    """
    Get client ip address.
    Detect ip address provided by HTTP_X_REAL_IP, HTTP_X_FORWARDED_FOR
    and REMOTE_ADDR meta headers.
    :param request: django request
    :return: ip address
    """
    real_ip = request.META.get('HTTP_X_REAL_IP')
    if real_ip:
        return real_ip
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

class Request:
    """
    Akismet request.
    Contains request specific data.
    """
    @classmethod
    def from_django_request(cls, request):
        """
        Create Akismet request from django HttpRequest.
        :type request: django.http.HttpRequest
        """
        return cls(
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            referrer=request.META.get('HTTP_REFERRER', ''),
        )

    def __init__(self, ip_address=None, user_agent=None, referrer=None):
        """
        :param ip_address: request ip address
        :param user_agent: request user agent
        :param referrer: request HTTP_REFERER meta
        """
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.referrer = referrer

    def as_params(self):
        """
        Converts object to Akismet request params.
        :rtype dict
        """
        return {
            'user_ip': self.ip_address,
            'user_agent': self.user_agent,
            'referrer': self.referrer,
        }


class Author:
    """
    Akismet author.
    Contains author specific data.
    """
    @classmethod
    def from_django_user(cls, user):
        """
        Create Akismet author from django user.
        :type user: django.contrib.auth.models.User
        """

        return cls(
            name=user.get_full_name(),
            email=user.email,
            role='administrator' if user.is_staff else None
        )

    def __init__(self, name=None, email=None, url=None, role=None):
        """
        :param name: user full name
        :param email: user email
        :param url: user website (url)
        :param role: user role, if administrator then Akismet
                     should not check it for spam.
        """
        self.name = name
        self.email = email
        self.role = role
        self.url = url

    def as_params(self):
        """
        Converts object to Akismet request params.
        :rtype dict
        """
        return {
            'comment_author': self.name,
            'comment_author_email': self.email,
            'comment_author_url': self.url,
            'user_role': self.role,
        }

class Site:
    """
    Akismet site (also known as `blog`).
    Contains site specific data.
    """
    def __init__(self, base_url=None, language_code=None):
        self.base_url = base_url
        self.language_code = language_code

    def as_params(self):
        """
        Converts object to Akismet request params.
        :rtype dict
        """

        return {
            'blog': self.base_url,
            'blog_lang': self.language_code,
        }

class Comment:
    """
    Akismet comment.
    Contains comment specific data, including author and site.
    """
    def __init__(self, content, type=None, permalink=None, author=None,
                 site=None):
        """
        :param content: comment text
        :param type: comment type (free form string relevant to comment type,
                     for example: feedback, post, ...)
        :param permalink: link to comment on site
        :param author: comment author
        :param site: comment site(blog)
        """
        self.content = content
        self.type = type
        self.permalink = permalink

        self.author = author
        self.site = site

        self.created = datetime.utcnow()

    def as_params(self):
        """
        Converts object to Akismet request params.
        :rtype dict
        """

        params = {
            'comment_type': self.type,
            'comment_content': self.content,
            'comment_date_gmt': self.created,
            'permalink': self.permalink,
        }

        if self.site:
            params.update(self.site.as_params())

        if self.author:
            params.update(self.author.as_params())
        return params