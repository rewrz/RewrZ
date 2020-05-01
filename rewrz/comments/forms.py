from django import forms
from .models import Comment
from captcha.fields import CaptchaField # 验证码

class CommentForm(forms.ModelForm):
    name = forms.CharField(required=True,widget=forms.TextInput(attrs={'class': 'validate', 'id': 'nick_name', 'type': 'text', 'placeholder': '*必填（公开）'}))
    email = forms.EmailField(required=True,widget=forms.TextInput(attrs={'class': 'validate', 'id': 'email', 'type': 'email', 'placeholder': '*必填（不会公开）'}))
    url = forms.URLField(required=False,widget=forms.URLInput(attrs={'id': 'input_text', 'length': '20', 'type': 'text', 'placeholder': '选填（公开）'}))
    text = forms.CharField(required=True,widget=forms.Textarea(attrs={'class': 'materialize-textarea validate','id': 'comment-textarea', 'length': '800', 'placeholder': '*必填（公开）'}))
    # parent = forms.IntegerField(required=False,widget=forms.TextInput(attrs={'type': 'hidden', 'placeholder': '父评论ID', 'readonly': 'readonly'}))
    captcha = CaptchaField(required=True)
    class Meta:
        model = Comment
        fields = ['name', 'email', 'url', 'text']