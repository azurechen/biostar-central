import logging
import re
from django.conf import settings
from biostar.message import models, auth
from biostar.accounts.models import Profile
from django.contrib.auth import get_user_model

User = get_user_model()

logger = logging.getLogger("engine")

HAS_UWSGI = False

COUNTER = 1


def parse_mentioned_users(content):

    # Any word preceded by a @ is considered a user handler.
    handler_pattern = "\@[^\s]+"
    # Drop leading @
    users_list = set(x[1:] for x in re.findall(handler_pattern, content))

    return User.objects.filter(username__in=users_list)


try:

    from uwsgidecorators import *

    HAS_UWSGI = True

    @spool(pass_arguments=True)
    def async_create_messages(subject, sender, body, rec_list, source=models.Message.MENTIONED, parent=None, uid=None):
        """
        Create messages to users in recipient list
        """
        # Assign a task to a a worker
        auth.create_local_messages(body=body, subject=subject, rec_list=rec_list, sender=sender, source=source,
                                   parent=parent, uid=uid)


except (ModuleNotFoundError, NameError) as exc:
    HAS_UWSGI = False
    # Bail out and record error
    logger.error(exc)
    pass


def parse_mention_msg(post):
    title = post.title
    mentioned_users = parse_mentioned_users(content=post.content)
    defalut_body = f"""
            Hello, You have been mentioned in a post by {post.author.profile.name}.
            The root post is :{title}.
            Here is where you are mentioned :
            {post.content}
            """
    subject = f"Mentioned in a post."

    return defalut_body, subject, mentioned_users


def parse_subs_msg(post, subs):
    title = post.title
    # Load template if its available
    default_body = f"""
          Hello,\n
          There is an addition by {post.author.profile.name} to a post you are subscribed to.\n
          Post: {title}\n
          Addition: {post.content}\n
          """
    users_id_list = subs.values_list("user", flat=True).distinct()

    subbed_users = User.objects.filter(id__in=users_id_list)

    subject = f"Subscription to a post."

    return default_body, subject, subbed_users


def send_message(subject, body, rec_list, sender, source=models.Message.REGULAR, parent=None, uid=None):
    # Create asynchronously when uwsgi is available
    if HAS_UWSGI:
        # Assign a worker to send mentioned users
        async_create_messages(source=source, sender=sender, subject=subject, body=body,
                              rec_list=rec_list, parent=parent, uid=uid)
        return
    # Can run synchrony only when debugging
    if settings.DEBUG:
        # Send subscription messages
        auth.create_local_messages(body=body, sender=sender, subject=subject, rec_list=rec_list,
                                   source=source, parent=parent, uid=uid)

    return


def send_notification_msgs(post):
    # Get the user meant to send subscriptions and notification messages.
    sender = User.objects.filter(is_superuser=True).first()

    # Parse the mentioned message
    ment_body, ment_subject, ment_users = parse_mention_msg(post=post)

    # Send the mentioned notifications
    send_message(source=models.Message.MENTIONED, subject=ment_subject, body=ment_body,
                 rec_list=ment_users, sender=sender)
    return


def send_subs_msg(post, subs):
    # Get the user meant to send subscriptions and notification messages.
    sender = User.objects.filter(is_superuser=True).first()

    # Parse the subscribed message
    sub_body, sub_subject, sub_users = parse_subs_msg(post=post, subs=subs)

    # Send message to subscribed users.
    send_message(subject=sub_subject, body=sub_body, rec_list=sub_users, sender=sender)

    return


