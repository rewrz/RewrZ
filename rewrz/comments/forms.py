from django import forms
from .models import Comment

class CommentForm(forms.ModelForm):
    name = forms.CharField(required=True,widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '昵称'}))
    email = forms.EmailField(required=True,widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '邮件地址'}))
    url = forms.URLField(required=False,widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': '网址'}))
    text = forms.CharField(required=True,widget=forms.Textarea(attrs={'class': 'form-control','id': 'comment-textarea', 'placeholder': '评论正文'}))
    # parent = forms.IntegerField(required=False,widget=forms.TextInput(attrs={'type': 'hidden', 'placeholder': '父评论ID', 'readonly': 'readonly'}))
    class Meta:
        model = Comment
        fields = ['name', 'email', 'url', 'text']