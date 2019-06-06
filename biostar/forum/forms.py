
from pagedown.widgets import PagedownWidget
from django import forms

from django.core.exceptions import ValidationError
from django.conf import settings
from biostar.accounts.models import User
from .models import Post
from biostar.forum import models

from .const import *

# Share logger with models
logger = models.logger

MIN_CHARS = 5
MAX_CONTENT = 15000
MIN_CONTENT = 10

def english_only(text):

    try:
        text.encode('ascii')
    except Exception:
        raise ValidationError('Title may only contain plain text (ASCII) characters')


def valid_title(text):
    "Validates form input for tags"
    text = text.strip()
    if not text:
        raise ValidationError('Please enter a title')

    text = text.replace(" ", '')
    if len(text) < MIN_CHARS:
        raise ValidationError(f'Too short, please add more than {MIN_CHARS} characters.')


def valid_tag(text):
    "Validates form input for tags"

    words = text.split(",")
    if len(words) > 5:
        raise ValidationError('You have too many tags (5 allowed)')


class PostLongForm(forms.Form):
    choices = [opt for opt in Post.TYPE_CHOICES if opt[0] in Post.TOP_LEVEL]
    post_type = forms.IntegerField(label="Post Type",
                                   widget=forms.Select(choices=choices, attrs={'class': "ui dropdown"}),
                                   help_text="Select a post type: Question, Forum, Job, Blog")
    title = forms.CharField(label="Post Title", max_length=200, min_length=2,
                            validators=[valid_title, english_only],
                            help_text="Descriptive titles promote better answers.")
    tag_val = forms.CharField(label="Post Tags", max_length=50, required=False, validators=[valid_tag],
                              help_text="""
                              To create a new tag just type and add a comma or press ENTER or SPACE.
                              """,
                              widget=forms.HiddenInput())
    content = forms.CharField(widget=PagedownWidget(template="widgets/pagedown.html"), validators=[english_only],
                              min_length=MIN_CONTENT, max_length=MAX_CONTENT, label="Enter your post below")

    def __init__(self, post=None, user=None, *args, **kwargs):
        self.post = post
        self.user = user
        super(PostLongForm, self).__init__(*args, **kwargs)

    def edit(self):
        """
        Edit an existing post.
        """
        if self.user != self.post.author and not self.user.profile.is_moderator:
            raise forms.ValidationError("Only the author or a moderator can edit a post.")
        data = self.cleaned_data
        self.post.title = data.get('title')
        self.post.content = data.get("content")
        self.post.type = data.get('post_type')
        self.post.tag_val = data.get('tag_val')
        self.post.save()
        return self.post

    def clean_tag_val(self):
        """
        Take out duplicates
        """
        tag_val = self.cleaned_data["tag_val"]
        tags = set(tag_val.split(","))
        return ",".join(tags)



class PostShortForm(forms.Form):
    MIN_LEN, MAX_LEN = 10, 10000
    parent_uid = forms.CharField(widget=forms.HiddenInput(), min_length=2, max_length=32)
    content = forms.CharField(widget=PagedownWidget(template="widgets/pagedown.html"),
                              min_length=MIN_LEN, max_length=MAX_LEN)

    def __init__(self, user=None, post=None, *args, **kwargs):
        self.user = user
        self.post = post
        super().__init__(*args, **kwargs)
        self.fields['content'].strip = False

    def edit(self):
        data = self.cleaned_data

        content = data.get("content")

        if self.user != self.post.author and not self.user.profile.is_moderator:
            raise forms.ValidationError("Only the author or a moderator can edit a post.")

        self.post.content = content
        self.post.save()
        return self.post



class CommentForm(forms.Form):

    post_uid = forms.CharField(widget=forms.HiddenInput(), min_length=2, max_length=5000)
    content = forms.CharField( widget=forms.Textarea,min_length=2, max_length=5000)


class PostModForm(forms.Form):

    CHOICES = [
        (BUMP_POST, "Bump a post"),
        (MOD_OPEN, "Open a closed or deleted post"),
        (TOGGLE_ACCEPT, "Toggle accepted status"),
        (MOVE_TO_ANSWER, "Move post to an answer"),
        (DELETE, "Delete post"),
    ]

    action = forms.IntegerField(widget=forms.RadioSelect(choices=CHOICES), label="Select Action", required=False )
    dupe = forms.CharField(required=False, max_length=200,
                           help_text="""One or more duplicated link, 
                                        comma separated (required for duplicate closing).
                                       """,
                           label="Duplicate Link(s)")
    pid = forms.CharField(required=False, max_length=200,
                           help_text=""" Parent uid to move comment under.
                                     """,
                           label="Duplicate Link(s)")

    def __init__(self, post, request, user, *args, **kwargs):
        self.post = post
        self.user = user
        self.request = request
        super(PostModForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(PostModForm, self).clean()
        action = cleaned_data.get("action")
        dupe = cleaned_data.get("dupe")
        pid = cleaned_data.get("pid").strip()
        cleaned_data["pid"] = pid

        if (action is None) and not (dupe or pid):
            raise forms.ValidationError("Select an action")

        if not (self.user.profile.is_moderator or self.user.profile.is_manager):
            raise forms.ValidationError("Only a moderator/manager may perform these actions")

        if action in (DUPLICATE, BUMP_POST) and not self.post.is_toplevel:
            raise forms.ValidationError("You can only perform these actions to a top-level post")
        if action in (TOGGLE_ACCEPT, MOVE_TO_COMMENT) and self.post.type != Post.ANSWER:
            raise forms.ValidationError("You can only perform these actions to an answer.")
        if action == MOVE_TO_ANSWER and self.post.type != Post.COMMENT:
            raise forms.ValidationError("You can only perform these actions to a comment.")

        parent = Post.objects.filter(uid=pid).first()
        if not parent and pid:
            raise forms.ValidationError(f"Parent uid : {parent} does not exist.")

        if parent and parent.root != self.post.root:
            raise forms.ValidationError(f"Parent does not share the same root.")

        if dupe:
            dupe = dupe.replace(",", " ")
            dupes = dupe.split()[:5]
            cleaned_data['dupe'] = dupes

        return cleaned_data




