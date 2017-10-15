from django.shortcuts import render, get_object_or_404, redirect
from blog.models import Post
from comments.models import Comment
from .forms import CommentForm

# Create your views here.

def post_comment(request, post_pk):
    post = get_object_or_404(Post, pk=post_pk)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            if request.POST.get('parent') is None:
                comment.parent = None
            else:
                comment.parent = Comment.objects.get(pk=int(request.POST.get('parent')))
            comment.save()
            return redirect(post)

        else:
            comment_list = post.comment_set.all().order_by('-created_time')
            context = {'post': post,
                       'form': form,
                       'comment_list': comment_list
                       }
            return render(request, 'blog/detail.html', context=context)
    return redirect(post)