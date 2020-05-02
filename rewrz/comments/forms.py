from django import forms
from .models import Comment
from captcha.fields import CaptchaField # 验证码
from rewrz import spam_check # 垃圾评论检测

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

    # 垃圾评论检测
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(CommentForm, self).__init__(*args, **kwargs)

    def clean(self):
        if self.request and spam_check.check(
                request = spam_check.Request.from_django_request(self.request),
                comment = spam_check.Comment(
                    content = self.cleaned_data['text'],
                    type = 'comment',
                    author = spam_check.Author(
                        name = self.cleaned_data['name'],
                        email = self.cleaned_data['email']
                    )
                )
        ):
            print('Spam detected')
            raise forms.ValidationError('Spam detected', code='spam-protection')
        return super().clean()

    # def save(self, **kwargs):
    #     self.clean()
    #     return super(CommentForm, self).save(**kwargs)