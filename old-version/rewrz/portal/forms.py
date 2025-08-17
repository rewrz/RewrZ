from django import forms
from django.contrib.auth.models import User
import re


def email_check(email):
    pattern = re.compile(r"\"?([-a-zA-Z0-9.`?{}]+@\w+\.\w+)\"?")
    return re.match(pattern, email)


class RegistrationForm(forms.Form):

    username = forms.CharField(label='登录用户名', max_length=50)
    email = forms.EmailField(label='邮箱地址',)
    password1 = forms.CharField(label='密码', widget=forms.PasswordInput)
    password2 = forms.CharField(label='重复密码', widget=forms.PasswordInput)

    # Use clean methods to define custom validation rules

    def clean_username(self):
        username = self.cleaned_data.get('username')

        if len(username) < 6:
            raise forms.ValidationError("你的名字必须大于6个字符。")
        elif len(username) > 50:
            raise forms.ValidationError("你的名字太长。")
        else:
            filter_result = User.objects.filter(username__exact=username)
            if len(filter_result) > 0:
                raise forms.ValidationError("你的名字已被注册。")

        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')

        if email_check(email):
            filter_result = User.objects.filter(email__exact=email)
            if len(filter_result) > 0:
                raise forms.ValidationError("你的邮箱已被注册。")
        else:
            raise forms.ValidationError("请输入验证邮箱。")

        return email

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')

        if len(password1) < 6:
            raise forms.ValidationError("你的密码太短。")
        elif len(password1) > 20:
            raise forms.ValidationError("你的密码太长。")
        return password1

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("密码不相符，请重新输入。")

        return password2


class LoginForm(forms.Form):

    username = forms.CharField(label='登录用户名', max_length=50)
    password = forms.CharField(label='登录密码', widget=forms.PasswordInput)

    # Use clean methods to define custom validation rules

    def clean_username(self):
        username = self.cleaned_data.get('username')

        if email_check(username):
            filter_result = User.objects.filter(email__exact=username)
            if not filter_result:
                raise forms.ValidationError("该邮箱还未注册。")
        else:
            filter_result = User.objects.filter(username__exact=username)
            if not filter_result:
                        raise forms.ValidationError("该用户还未注册，请先注册。")

        return username