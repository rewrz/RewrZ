from django.shortcuts import render, get_object_or_404, redirect, HttpResponse, Http404
from blog.models import Post
from comments.models import Comment
from .forms import CommentForm
from captcha.models import CaptchaStore # 验证码
from captcha.helpers import captcha_image_url # 验证码
from django.http import JsonResponse # ajax json

# 创建验证码
def captcha():
    hashkey = CaptchaStore.generate_key()
    image_url = captcha_image_url(hashkey)
    captcha = {'hashkey': hashkey, 'image_url': image_url}
    print(captcha)
    return captcha

# ajax 验证验证码
def check_captcha(request):
    if  request.is_ajax():
        cs = CaptchaStore.objects.filter(response=request.GET['response'].lower(),
                                     hashkey=request.GET['hashkey'])
        if cs:
            json_data={'status':1}
        else:
            json_data = {'status':0}
        return JsonResponse(json_data)
    else:
        # raise Http404
        json_data = {'status':0}
        return JsonResponse(json_data)


# 刷新验证码
# path: /ims/refresh_captcha
import json
def refresh_captcha(request):
    """
    Return json with new captcha for ajax refresh request
    """
    if not request.is_ajax(): # 只接受ajax提交
        raise Http404
    new_captcha = captcha()
    return HttpResponse(json.dumps(new_captcha), content_type='application/json')

# 提交评论
def post_comment(request, post_pk):
    post = get_object_or_404(Post, pk=post_pk)
    if request.method == 'POST':
        form = CommentForm(request.POST, request=request)

        if form.is_valid():
            new_comment = form.save(commit=False)
            new_comment.post = post
            if request.POST.get('parent') == '' or request.POST.get('parent') is None:
                new_comment.parent = None
            else:
                # 二级评论处理
                parent_comment = Comment.objects.get(pk=int(request.POST.get('parent')))
                new_comment.parent_id = parent_comment.get_root().id
                new_comment.reply_to = parent_comment
                new_comment.save()
                #return HttpResponse('200 OK')
            new_comment.save()
            return redirect(post)
        else:
            return render(request, 'portal/error/403.html')
    elif request.method == 'GET':
        form = CommentForm()
        comment_list = post.comment_set.all().order_by('-created_time')
        context = {'post': post,
                   'form': form,
                   'comment_list': comment_list,
                  }
        return render(request, 'blog/detail.html', context=context)
    else:
        return HttpResponse("请求错误。")